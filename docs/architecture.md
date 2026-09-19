# Architecture

See `PRD.md` for the product context. This describes the technical plan for the full build.
`spike/` started as a Phase 0 proof of concept but now implements nearly everything described
below: the browser-mic transport, doctor intro, condition branching via a real Supabase
`patients` lookup, the full 6-question loop (both the HOOS JR and stroke sets) with confirmation
classification and bounded clarification retries, the standard confirmation template, closing
script, the full live gait-checker handoff (SMS link, walkthrough guidance/countdown, survey
submission), and Supabase persistence (`calls`, `call_responses`, `gait_check_links`) — see
`spike/README.md`. What's still missing: a real review dashboard and any automation for
triggering calls (`packages/server/`/`packages/dashboard/` per the target repo structure below
don't exist yet as separate packages).

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
  → OUTRO → SEND_SMS_LINK → WALKTHROUGH_GUIDANCE → WALKTHROUGH_COUNTDOWN → WALKTHROUGH_OBSERVE
  → HANGUP → PERSIST
```

The call **stays on the line** through the gait check rather than ending after the survey — the
patient shouldn't be dropped and left to figure out a camera setup alone. This "companion,
hand-holding" framing (stay with the patient through both the talking part and the physical
part) is a deliberate product choice, not just a technical one.

- **DOCTOR_INTRO**: a spoken introduction (recorded clip or TTS-voiced script — an
  implementation choice, not decided here) establishing who's calling and why, before any
  question is asked.
- **LOOKUP_CONDITION**: reads the patient's `condition_category` (`'orthopedic' | 'stroke'`)
  and selects the matching 6-question set — `survey/hoos-jr-hip.json` for orthopedic,
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
- **OUTRO**: after the last question is confirmed, a short thank-you, e.g. *"Thank you so much
  for your time today."* Fixed, spoken line, not model-generated.
- **SEND_SMS_LINK**: text the patient their personalized gait-checker link (see "Integration
  contract" below for the endpoint/shape) using `patients.phone_number`, then speak a fixed
  confirmation line: *"I've just texted you a secure link. Go ahead and open it on your phone
  or computer."* SMS requires a messaging provider — see the note on that dependency below;
  falling back to just speaking/displaying the URL (no real text message) is an acceptable
  hackathon-demo degradation if SMS isn't wired up in time.
- **WALKTHROUGH_GUIDANCE**: while still on the line, the AI walks the patient through getting
  into position, step by step, matching what the gait checker's own on-screen UI shows them
  (per the handoff spec, their page displays matching visual cues) — e.g. *"Tap the 'Live
  Camera' mode, prop your device up against a stable surface where your full body is visible,
  and step back a few paces."* Fixed script, not model-generated — this is instructional, not a
  point where free-text patient answers need mapping.
- **WALKTHROUGH_COUNTDOWN**: *"When you're ready, I'll count to three, and you can walk slowly
  across the frame from left to right,"* then a spoken three-count. Simple fixed TTS lines; no
  STT/mapping involved.
- **WALKTHROUGH_OBSERVE**: a short wait while the patient walks (the AI has no visibility into
  the gait checker's own capture — it's purely a timed pause plus a closing remark, e.g. *"Great,
  thank you!"*), then `HANGUP`. The gait checker's own page is what actually captures/analyzes
  the walk; this state exists to keep the call itself feeling attentive, not to do any gait
  analysis on the voice side. **Be honest about what this currently is**: a fixed-duration
  timer (`spike/`'s is 5 seconds), not an adaptive wait — the AI has no signal for whether the
  patient has actually opened the link, granted camera permission, and gotten into position, all
  of which realistically take longer than a few seconds. Fine as a hackathon simplification
  (predictable, easy to rehearse), but it should be described as "the AI waits a bit" rather
  than "the AI waits for the patient to be ready." A real fix would have the gait checker's page
  push a "camera ready" signal back (e.g. over a small webhook or shared realtime channel) that
  this state actually waits on — noted as a stretch idea, not built now.
- **PERSIST**: after `HANGUP`, submit the call's data — survey answers plus a
  `walkthrough_completed` flag (see "Integration contract" below) — to the gait checker's
  backend in one request, and save the full transcript/structured answers to our own Supabase
  tables.
- No full-duplex barge-in in the MVP — strict turn-taking (wait for a "TTS finished playing"
  signal before opening the mic) avoids a large class of race conditions that would hurt
  live-demo reliability. Can be added later if time allows.
- **Implemented in `spike/`**: `SEND_SMS_LINK` through `PERSIST` all run (`src/server.ts`,
  `src/gaitCheckerClient.ts`, `src/smsSender.ts`); `PERSIST` there only submits to the gait
  checker (no Supabase yet, since the spike has no database — see `spike/README.md`).

## Integration contract with the gait checker

The gait checker (a separate teammate's repo/deployment — working name **GaitGuard**, a
Next.js frontend + FastAPI backend with its own live-MediaPipe/simulated-fallback gait
analysis) is not part of this repo. The two systems divide responsibility cleanly:

- **This repo (voice call) owns**: the conversation (including staying on the line through the
  gait-check walkthrough — see the state machine above), the 6-question structured survey
  answers, and — per the handoff spec agreed with that teammate — texting the patient their
  personalized link mid-call and submitting the survey answers (plus a walkthrough-completed
  flag) to their backend once the call ends.
- **The gait checker repo owns**: gait capture/analysis, the personalized patient page, **and
  the doctor-facing unified clinical report** that merges subjective survey data with objective
  gait telemetry and an AI-generated clinical synthesis. That report is built and hosted
  entirely in their repo, not this one — this repo does not need to receive gait results back,
  build its own merged clinical view, or expose a results-receiving webhook. (This simplifies
  the "Data model" section below vs. earlier drafts of this doc that assumed we might need a
  `gait_reports` table on our side — we don't; their backend is the merge point.)

There are now two separate outbound mechanisms, at different points in the call — don't
conflate them:

**1. Personalized link (at `SEND_SMS_LINK`, mid-call, before any data is submitted)**: the link
is a deterministic URL from the patient's code, not something returned by an API call, so it
can be generated and texted before the survey data is ever submitted:

```
https://<gait-checker-domain>/patient/<patient_code>
```

e.g. `https://gaitguard.ai/patient/RGN-0417`. The base domain should come from an env var
(e.g. `GAIT_CHECKER_BASE_URL`), not be hardcoded, since it'll change between their
dev/staging/demo deployments. Delivering it requires an SMS provider — this is a **new external
dependency** (the project dropped Twilio's Voice/Media Streams product in the browser-mic
pivot, but sending a text is a much lighter integration: one HTTP call, no telephony audio
handling — Twilio's Messaging API or a similar provider both work). Falling back to just
speaking/displaying the URL if SMS isn't wired up in time is an acceptable hackathon-demo
degradation (see `WALKTHROUGH_GUIDANCE`'s note above).

**2. Survey + walkthrough data handoff (at `PERSIST`, after `HANGUP`, once)**: `POST` to their
FastAPI endpoint:

```
POST https://<gait-checker-domain>/api/submit-survey
Content-Type: application/json

{
  "patient_id": "RGN-0417",
  "timestamp": "2026-09-19T17:38:00Z",
  "walkthrough_completed": true,
  "survey_responses": {
    "pain_scale_1_to_10": 4,
    "recent_falls": 1,
    "primary_complaint": "Stiffness in right knee"
  }
}
```

- `patient_id` is the same **human-readable external code** as the link path (e.g.
  `RGN-0417`), not our internal Supabase `patients.id` UUID — see `patient_code` in the data
  model below.
- `walkthrough_completed` is a simple boolean: did the call make it through
  `WALKTHROUGH_OBSERVE` before hanging up, or did the patient drop off earlier (e.g. during the
  survey, or mid-walkthrough)? This repo has no way to know whether the patient actually
  completed the physical walk — only whether our side of the call reached that point — so treat
  it as "our call flow finished," not as gait-checker-verified completion.
- `survey_responses` is a flat, human-readable key/value object — not our internal
  `call_responses` row shape. Build it from that call's confirmed answers, keyed by each
  question's `code` (or a friendlier per-question key) with the matched answer's label or raw
  value (e.g. a 0–10 question sends the number, a labeled-scale question sends the label
  string, matching the mixed style in the example above).
- **Failure handling**: if this `POST` fails (their service is down, network error, etc.), the
  patient has already received their link (sent earlier, independently) — don't block or retry
  indefinitely; flag the call for follow-up (e.g. `gait_check_links.status = 'submit_failed'`)
  and move on.
- This contract can still change (it reflects the current handoff spec, not a finalized API);
  treat exact field names as the best current information, confirm against their actual FastAPI
  route before wiring up real code.

## Data model (Supabase / Postgres)

**This schema is provisioned** — a Supabase project (`voiceaithing-hackmit`) exists with this
exact schema applied and RLS enabled with permissive "allow all" policies (functionally the
same as the "left permissive" note below, without triggering Supabase's "RLS disabled" security
advisory). `spike/.env.example` has the real `SUPABASE_URL`/`SUPABASE_ANON_KEY` for it — see
`spike/README.md` for seeding. It's a hackathon-only project with no real patient data (two
demo patients: `RGN-0417` orthopedic, `RGN-0500` stroke).

```sql
create table patients (
  id uuid primary key default gen_random_uuid(),
  patient_code text unique not null,   -- human-readable external ID shared with the gait checker, e.g. 'RGN-0417'
  full_name text not null,
  phone_number text not null,          -- E.164
  condition_category text not null,    -- 'orthopedic' | 'stroke' -- drives question-set + gait exercise-set selection
  procedure_type text,                 -- e.g. 'total_knee_arthroplasty', 'total_hip_arthroplasty' (orthopedic only)
  procedure_date date,
  created_at timestamptz default now()
);

create table survey_questions (
  id uuid primary key default gen_random_uuid(),
  question_set_code text not null,     -- 'HOOS_JR_V1_HIP' | 'STROKE_SUBSET_V1'
  code text unique not null,           -- e.g. 'HOOS_STAIRS'
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
  submitted_survey_data boolean not null default false, -- did the POST to /api/submit-survey succeed?
  sent_at timestamptz default now(),
  status text not null default 'sent'  -- 'sent' | 'submit_failed'
);
```

Row Level Security is left permissive for the hackathon demo (single-tenant); production would
need RLS and auth given this is PHI-adjacent data. No `gait_reports` table is needed on this
side — per the integration contract above, the gait checker's own backend is where survey
answers and gait telemetry are merged into the doctor-facing clinical report, not here.

## Question banks

- `survey/hoos-jr-hip.json` — the **real, validated HOOS, JR.** (Hip disability and
  Osteoarthritis Outcome Score for Joint Replacement) instrument, English version 1.0,
  ©2016 Hospital for Special Surgery — not a hackathon approximation. All 6 items share one
  None/Mild/Moderate/Severe/Extreme scale: pain going up/down stairs and on uneven surfaces;
  difficulty rising from sitting, bending to the floor, lying in bed, and sitting. It's
  hip-specific (KOOS JR is this instrument's knee counterpart, not included here). Production
  or commercial use would need licensing terms confirmed with Hospital for Special Surgery —
  distinct from using it in this demo for its stated clinical purpose.
- `survey/stroke-subset.json` — a hackathon-representative 6-question set modeled on domains
  common to standardized stroke recovery screens (e.g. mobility/balance,
  weakness/coordination, speech/communication effects, activities-of-daily-living
  independence, mood, and fall history). Unlike the HOOS JR file, this one is **not** a real
  named validated instrument — it's our own approximation, flagged as such in the file itself.
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
│   ├── hoos-jr-hip.json        # orthopedic (hip), real HOOS JR instrument, 6 questions
│   └── stroke-subset.json      # stroke, 6 questions
├── packages/
│   ├── server/                 # Express/Fastify + ws
│   │   └── src/
│   │       ├── routes/calls.ts       # POST /calls, GET /calls, GET /calls/:id
│   │       ├── ws/browserStream.ts   # browser mic<->Deepgram bridge + drives the state machine
│   │       ├── call-flow/stateMachine.ts, questions.ts, conditionLookup.ts
│   │       ├── integrations/deepgramStt.ts, deepgramTts.ts, claudeMapper.ts,
│   │       │                gaitCheckerClient.ts (link + /api/submit-survey), smsSender.ts
│   │       └── db/supabaseClient.ts
│   └── dashboard/               # minimal React (Vite) app
├── scripts/seed-questions.ts
└── spike/                       # Phase 0 spike, browser-mic transport (see spike/README.md)
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
- **Gait-checker integration-contract risk**: the `POST /api/submit-survey` shape and
  `patient_code` scheme (§ Integration contract) come from the other teammate's spec, not a
  finalized/versioned API — confirm field names against their actual route before relying on
  them, and make the submission failure-tolerant (§ Integration contract's "Failure handling")
  so a change or outage on their end doesn't break call completion on ours.
- **New SMS dependency**: `SEND_SMS_LINK` needs a messaging provider and account setup (e.g.
  Twilio's Messaging API) that doesn't otherwise exist in the browser-mic design — budget setup
  time for this the same way the original spike budgeted time for Twilio Voice, even though
  sending a text is a much smaller integration than the telephony audio bridge that was
  removed. Fallback: speak/display the URL without a real text message (see `SEND_SMS_LINK`'s
  note above) if this isn't ready in time.
- **Staying on the line adds dead air risk**: `WALKTHROUGH_OBSERVE` is a timed pause with no way
  to know if the patient is actually following along (the voice side can't see the gait
  checker's camera feed) — keep it short and end with a warm, generic closing line regardless
  of what actually happened during the walk, rather than trying to infer anything from silence.
