# Architecture

See `PRD.md` for the product context. This describes the technical plan for the full build.
`spike/` is a Phase 0 proof of concept that currently reflects the **earlier Twilio phone-call
design** described in this repo's git history — it has not yet been updated for the
browser-mic pivot described below. Treat it as reference for the Claude tool-use mapping
pattern (`spike/src/claudeMapper.ts`), not as the current transport design.

## Call transport (browser, not telephony)

The hackathon demo runs entirely in-browser: no Twilio, no phone number, no ngrok.

- The patient's browser captures mic audio via `getUserMedia`, and streams PCM audio frames to
  our Node server over a plain WebSocket (an `AudioWorklet` or `MediaRecorder`-based capture
  pipeline both work; prefer `AudioWorklet` for lower latency and more control over frame size).
  Browser mic capture is typically linear16 PCM at 16kHz or higher, which Deepgram's STT
  accepts directly (`encoding=linear16&sample_rate=16000` or whatever rate the capture pipeline
  actually produces — match this exactly, it's the same class of "looks right in code, silent
  or garbled on a real run" risk that mulaw/8kHz was for the telephony design).
- TTS audio comes back over the same WebSocket and is played via the browser's `AudioContext`
  (schedule buffered playback rather than naively appending chunks, to avoid audible glitches
  between TTS chunks).
- This removes the entire class of Twilio-specific risk (number provisioning/verification,
  telephony audio format mismatches). The equivalent top risk now is **browser audio
  capture/playback correctness** — validate this in isolation (play a static TTS clip back
  through the browser, capture and transcribe a short live utterance) before building the full
  state machine on top of it, the same way the original spike validated telephony audio first.

## Voice pipeline

**Primary path:** our own server-side state machine orchestrates Deepgram streaming STT and
Deepgram TTS directly over the browser WebSocket, calling Claude between turns via forced
tool-use. This keeps full control over turn-taking and guarantees the AI can't free-chat,
since our server — not an LLM agent — decides every line that gets spoken. This part of the
design is unchanged by the transport pivot.

**Stretch path (only after the primary path works):** re-platform onto Deepgram's Voice Agent
API (bundles STT + LLM + TTS in one socket, function calling, `UpdatePrompt`,
`InjectAgentMessage`). Treat as an upgrade, not the base plan, for the same reason as before:
forcing the agent's own LLM to never free-chat is harder to guarantee than our server-driven
`tool_choice` approach.

**Turn-taking tuning:** default the silence/endpointing threshold to roughly **3000–4000ms**
(up from a typical voice-agent default) before the system assumes the patient is done talking.
This is a deliberate product decision, not just a technical tuning knob — both elderly
orthopedic patients and stroke patients (who may have speech effects) need more room than a
snappy voice-assistant default gives them. Back this with an independent server-side max-silence
timer in case Deepgram's own endpointing doesn't fire, same pattern as before.

## Call flow / state machine

One instance per active call:

```
INIT → DOCTOR_INTRO → LOOKUP_CONDITION → ASK_QUESTION(i) → LISTENING(i) → MAPPING(i)
  → CONFIRMING(i) → (yes) → next question, or OUTRO if last question
  → CLARIFYING(i) → back to LISTENING(i)  [bounded retries, e.g. max 2]
  → OUTRO → SEND_GAIT_LINK → HANGUP → PERSIST
```

- **DOCTOR_INTRO**: a spoken introduction (recorded clip or TTS-voiced script — an
  implementation choice, not decided here) establishing who's calling and why, before any
  question is asked.
- **LOOKUP_CONDITION**: reads the patient's `condition_category` (`'orthopedic' | 'stroke'`)
  and selects the matching 6-question set — `survey/koos-hoos-subset.json` for orthopedic,
  `survey/stroke-subset.json` for stroke (see "Question banks" below). This choice is made
  once, from the patient record, never asked to the patient and never improvised.
- **LISTENING**: stream patient audio to Deepgram STT until the tuned silence/endpointing gap
  (see "Turn-taking tuning" above) or the independent max-silence backstop fires.
- **MAPPING**: send the transcript plus that question's fixed answer schema to Claude with
  `tool_choice` forcing a `map_answer` tool call:
  `{mapped_value, confidence, needs_clarification, patient_facing_confirmation}`. This is the
  core data-integrity guarantee — the model can only return a structured mapping and the exact
  confirmation sentence to speak, never open-ended chat. `patient_facing_confirmation` must
  follow a **standard, recognizable template every time** — *"You said your \<topic\> was
  \<label\>, correct?"*, filling in the question's domain/topic and the matched answer option's
  label — rather than open-ended natural phrasing that could vary unpredictably question to
  question. This is a deliberate trust/consistency choice, not just a data-integrity one: a
  patient should be able to tell they're being confirmed the same way every time. The mechanism
  that produces it stays forced tool-use either way — see `CLAUDE.md`'s non-negotiable
  constraint.
- **CLARIFYING**: triggered by low confidence or a "no" on confirmation; ask one targeted
  disambiguating question, bounded retries, then fall back to `needs_human_review = true`
  rather than looping indefinitely.
- **OUTRO**: after the last question is confirmed, a short closing script — a thank-you plus a
  spoken mention that a gait-checker link is coming, e.g. *"Thank you so much for your time
  today. We'll send you a link shortly to complete a quick recording for the gait tracker."*
  This is a fixed, spoken line, not model-generated. At this stage the line is **spoken only**
  — actually generating/sending the link happens in the following `SEND_GAIT_LINK` state, and
  per the integration-contract note below, that link-delivery mechanism itself is still being
  built in the separate gait-checker repo.
- **SEND_GAIT_LINK**: once all 6 questions are answered and `OUTRO` has played, construct the
  gait-checker URL (see "Integration contract with the gait checker" below) and deliver it —
  spoken aloud, shown in the browser UI, and/or sent by SMS (stretch, needs a messaging
  provider — not required for the browser demo). **Deferred for now**: the user is building the
  gait checker in a separate repo, so this state's actual link generation/delivery logic is not
  yet implemented here; `OUTRO`'s spoken mention of "we'll send you a link" stands in for it in
  the interim.
- No full-duplex barge-in in the MVP — strict turn-taking (wait for a "TTS finished playing"
  signal before opening the mic) avoids a large class of race conditions that would hurt
  live-demo reliability. Can be added later if time allows.

## Integration contract with the gait checker

The gait checker is a separate, already-built system (its own repo/deployment, not part of
this one). This repo's only responsibility is generating and delivering a link at the end of
the call — it does not implement or depend on the gait checker's internals.

- **Outbound (this repo → gait checker)**: a URL carrying enough identifiers for the gait
  checker to know who it's testing and what to test, e.g.
  `https://<gait-checker-domain>/start?patient_id=<uuid>&call_id=<uuid>&exercise_set=<orthopedic|stroke>`.
  Keep this contract minimal (a link with a few query params) precisely because it's the seam
  between two independently-built systems under hackathon time pressure — every additional
  field is another thing that has to be agreed and kept in sync.
- **Inbound (gait checker → this repo), open item**: whether/how gait results get reported
  back (e.g. a results webhook this server exposes) is **not yet defined** — it depends on
  what the gait checker repo actually supports. Don't build speculative webhook-receiving code
  until that contract is confirmed; track it as an open integration point (see `gait_check_links`
  in the data model below, which records that a link was sent, not what came back).

## Data model (Supabase / Postgres)

```sql
create table patients (
  id uuid primary key default gen_random_uuid(),
  full_name text not null,
  phone_number text not null,          -- E.164
  condition_category text not null,    -- 'orthopedic' | 'stroke' -- drives question-set + gait exercise-set selection
  procedure_type text,                 -- e.g. 'total_knee_arthroplasty', 'total_hip_arthroplasty' (orthopedic only)
  procedure_date date,
  created_at timestamptz default now()
);

create table survey_questions (
  id uuid primary key default gen_random_uuid(),
  question_set_code text not null,     -- 'KOOS_HOOS_SUBSET_V1' | 'STROKE_SUBSET_V1'
  code text unique not null,           -- e.g. 'KOOS_PAIN_1'
  sequence_order int not null,
  domain text not null,                -- e.g. 'pain' | 'stiffness' | 'function' | 'qol' (orthopedic), or 'mobility' | 'balance' | ... (stroke)
  prompt_text text not null,           -- what the AI says on the call
  answer_options jsonb not null,       -- [{code:0,label:'None'},{code:1,label:'Mild'},...]
  is_active boolean default true
);

create table calls (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid references patients(id),
  call_type text not null,             -- 'pre_treatment' | 'post_3mo' | 'post_1yr' | 'post_5yr' | 'post_10yr'
  status text not null default 'initiated', -- initiated|in_progress|completed|incomplete|failed
  started_at timestamptz,
  ended_at timestamptz,
  full_transcript jsonb,               -- ordered array of {speaker, text, ts}
  created_at timestamptz default now()
);

create table call_responses (
  id uuid primary key default gen_random_uuid(),
  call_id uuid references calls(id) on delete cascade,
  question_id uuid references survey_questions(id),
  raw_patient_text text,
  mapped_value_code int,
  mapped_value_label text,
  llm_confidence numeric,
  confirmed_by_patient boolean default false,
  clarification_attempts int default 0,
  needs_human_review boolean default false,
  created_at timestamptz default now()
);

create table gait_check_links (
  id uuid primary key default gen_random_uuid(),
  call_id uuid references calls(id) on delete cascade,
  url text not null,
  exercise_set text not null,          -- 'orthopedic' | 'stroke'
  sent_at timestamptz default now(),
  status text not null default 'sent'  -- 'sent' -- extend once the gait checker's result-reporting contract is known
);
```

Row Level Security is left permissive for the hackathon demo (single-tenant); production would
need RLS and auth given this is PHI-adjacent data. `gait_reports` (or equivalent) is
deliberately not modeled yet — add it once the gait checker's actual result-delivery contract
is known, rather than guessing its shape now.

## Question banks

- `survey/koos-hoos-subset.json` — orthopedic knee/hip PROM, trimmed to the **6** questions
  that matter most for the demo (down from an earlier 8-question draft): pain, stiffness,
  walking difficulty, stair difficulty, quality-of-life awareness, and an overall 0–10 rating.
- `survey/stroke-subset.json` — a **new**, hackathon-representative 6-question set modeled on
  domains common to standardized stroke recovery screens (e.g. mobility/balance,
  weakness/coordination, speech/communication effects, activities-of-daily-living
  independence, mood, and fall history). Like the orthopedic file, this is explicitly a
  hackathon-representative subset, not a clinically validated instrument — flagged as such in
  the file itself.
- Both are seeded into `survey_questions`, scoped by `question_set_code`, and selected at
  `LOOKUP_CONDITION` based on the patient's `condition_category`.

## Repo structure (full build, target state)

```
VoiceAIThing/
├── LICENSE                     # MIT
├── PRD.md
├── CLAUDE.md
├── docs/architecture.md
├── survey/
│   ├── koos-hoos-subset.json   # orthopedic, 6 questions
│   └── stroke-subset.json      # stroke, 6 questions
├── packages/
│   ├── server/                 # Express/Fastify + ws
│   │   └── src/
│   │       ├── routes/calls.ts       # POST /calls, GET /calls, GET /calls/:id
│   │       ├── ws/browserStream.ts   # browser mic<->Deepgram bridge + drives the state machine
│   │       ├── call-flow/stateMachine.ts, questions.ts, conditionLookup.ts
│   │       ├── integrations/deepgramStt.ts, deepgramTts.ts, claudeMapper.ts, gaitLink.ts
│   │       └── db/supabaseClient.ts
│   └── dashboard/               # minimal React (Vite) app
├── scripts/seed-questions.ts
└── spike/                       # Phase 0 spike (currently reflects the pre-pivot Twilio design)
```

## Key risks & fallbacks

- **Browser audio format mismatch** (highest risk, replaces the old mulaw/telephony risk):
  validate with an isolated round-trip test — play a static TTS clip back through the browser,
  capture and transcribe a short live utterance — before building the state machine on top.
- **Endpointing tuned wrong for slower/effortful speech**: 3–4 second silence threshold plus an
  independent server-side max-silence backstop, tuned against real stroke- and elderly-patient
  speech patterns where possible, not just typical test speech.
- **Claude latency mid-call**: keep the `map_answer` tool schema small, use a fast model, keep
  connections warm.
- **Full-duplex/barge-in**: deliberately out of scope for the MVP.
- **Streaming too fragile to demo reliably**: fall back to a turn-based pipeline — buffer a
  full utterance, then run STT → Claude → TTS as discrete request/response steps instead of
  continuous streaming. The state machine already models each step discretely, so this is a
  config/timing change, not a redesign.
- **Gait-checker integration-contract risk**: keep the outbound link minimal (§ Integration
  contract) so the handoff doesn't depend on details of a system this repo doesn't control.
