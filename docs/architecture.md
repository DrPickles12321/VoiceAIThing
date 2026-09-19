# Architecture

See `PRD.md` for the product context. This describes the technical plan for the full build
(as opposed to `spike/`, which is a minimal Phase 0 proof of concept for the riskiest part of
this design).

## Call transport

Outbound call via **Twilio**: `POST /calls` on our server calls `twilioClient.calls.create()`
with a `url` pointing at our `/twiml` endpoint, which returns TwiML containing
`<Connect><Stream url="wss://.../media" /></Connect>`. Twilio then opens a bidirectional
WebSocket to our server and streams call audio both ways as JSON `media` events whose
`payload` is base64-encoded **mu-law audio at 8kHz**, with no container.

We request the exact same format directly from Deepgram in both directions — STT `listen`
accepts `encoding=mulaw&sample_rate=8000`, and TTS `speak` can output
`encoding=mulaw&sample_rate=8000&container=none` — so audio passes through the whole pipeline
with **zero transcoding**. Getting this format plumbing right is the single highest-risk,
highest-priority technical detail (see `spike/`), since a subtle mismatch (wrong sample rate,
extra headers, wrong frame size) tends to look correct in code review but produces garbled or
silent audio on a real call.

Twilio message types to handle: `connected`, `start` (carries `streamSid`), `media` (repeated),
`mark` (echoed back to us once audio we sent has finished playing — used for turn-taking), and
`stop`.

## Voice pipeline

**Primary path (build first):** our own server-side state machine orchestrates Deepgram
streaming STT and Deepgram TTS directly, calling Claude between turns via forced tool-use.
This keeps full control over turn-taking and guarantees the AI can't free-chat, since our
server — not an LLM agent — decides every line that gets spoken.

**Stretch path (only after the primary path works):** re-platform onto Deepgram's Voice Agent
API, a single bidirectional socket that bundles STT + LLM ("think", can be pointed at Claude
directly) + TTS, with function calling, `UpdatePrompt`, and `InjectAgentMessage`. Higher
potential "wow" factor in a demo, but materially harder to guarantee the agent's LLM never
free-chats — treat as an upgrade, not the base plan.

## Call flow / state machine

One instance per active call:

```
INIT → INTRO → ASK_QUESTION(i) → LISTENING(i) → MAPPING(i)
  → CONFIRMING(i) → (yes) → next question, or OUTRO if last question
  → CLARIFYING(i) → back to LISTENING(i)  [bounded retries, e.g. max 2]
  → OUTRO → HANGUP → PERSIST
```

- **LISTENING**: stream patient audio to Deepgram STT until an endpointing/silence gap, tuned
  generously since elderly patients pause and ramble, backed by an independent server-side
  max-silence timer in case Deepgram's own endpointing doesn't fire.
- **MAPPING**: send the transcript plus that question's fixed answer schema to Claude with
  `tool_choice` forcing a `map_answer` tool call:
  `{mapped_value, confidence, needs_clarification, patient_facing_confirmation}`. This is the
  core data-integrity guarantee — the model can only return a structured mapping and the exact
  confirmation sentence to speak, never open-ended chat.
- **CLARIFYING**: triggered by low confidence or a "no" on confirmation; ask one targeted
  disambiguating question, bounded retries, then fall back to `needs_human_review = true`
  rather than looping indefinitely.
- No full-duplex barge-in in the MVP — strict turn-taking (wait for the Twilio `mark` event
  signaling our TTS finished, then open the mic) avoids a large class of race conditions that
  would hurt live-demo reliability. Can be added later if time allows.

## Data model (Supabase / Postgres)

```sql
create table patients (
  id uuid primary key default gen_random_uuid(),
  full_name text not null,
  phone_number text not null,          -- E.164
  procedure_type text,                 -- e.g. 'total_knee_arthroplasty', 'total_hip_arthroplasty'
  procedure_date date,
  created_at timestamptz default now()
);

create table survey_questions (
  id uuid primary key default gen_random_uuid(),
  code text unique not null,           -- e.g. 'KOOS_PAIN_1'
  sequence_order int not null,
  domain text not null,                -- 'pain' | 'stiffness' | 'function' | 'qol'
  prompt_text text not null,           -- what the AI says on the call
  answer_options jsonb not null,       -- [{code:0,label:'None'},{code:1,label:'Mild'},...]
  is_active boolean default true
);

create table calls (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid references patients(id),
  twilio_call_sid text unique,
  call_type text not null,             -- 'pre_op' | 'post_op_3mo' | 'post_op_1yr' | 'post_op_5yr' | 'post_op_10yr'
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
```

Row Level Security is left permissive for the hackathon demo (single-tenant); production would
need RLS and auth given this is PHI-adjacent data.

## Demo survey

Eight KOOS/HOOS-styled questions covering pain, stiffness, function (walking / stairs /
rising from sitting), and quality of life, plus an overall 0–10 rating. Stored as JSON at
`survey/koos-hoos-subset.json` (full build) and seeded into `survey_questions`. `spike/`
currently hardcodes just the first pain question.

## Repo structure (full build, target state)

```
VoiceAIThing/
├── LICENSE                     # MIT
├── PRD.md
├── CLAUDE.md
├── docs/architecture.md
├── survey/koos-hoos-subset.json
├── packages/
│   ├── server/                 # Express/Fastify + ws
│   │   └── src/
│   │       ├── routes/calls.ts       # POST /calls, GET /calls, GET /calls/:id
│   │       ├── routes/twiml.ts       # returns <Connect><Stream> TwiML
│   │       ├── ws/mediaStream.ts     # Twilio<->Deepgram bridge + drives the state machine
│   │       ├── call-flow/stateMachine.ts, questions.ts
│   │       ├── integrations/deepgramStt.ts, deepgramTts.ts, claudeMapper.ts, twilioClient.ts
│   │       └── db/supabaseClient.ts
│   └── dashboard/               # minimal React (Vite) app
├── scripts/seed-questions.ts
└── spike/                       # Phase 0 feasibility spike (see spike/README.md)
```

## Key risks & fallbacks

- **Mulaw/8kHz format mismatch** (highest risk): validate with an isolated test — play a
  static TTS clip through the bridge to a real phone — before building the state machine on
  top of it. This is exactly what `spike/` does.
- **Twilio number/verification delays**: provision and verify test numbers immediately, not
  midway through the build.
- **STT endpointing too aggressive/lenient for rambling, elderly speech**: tune
  `endpointing`/`utterance_end_ms` plus an independent server-side max-silence backstop.
- **Claude latency mid-call**: keep the `map_answer` tool schema small, use a fast model, keep
  connections warm.
- **Full-duplex/barge-in**: deliberately out of scope for the MVP.
- **Streaming too fragile to demo reliably**: fall back to a turn-based pipeline — buffer a
  full utterance, then run STT → Claude → TTS as discrete request/response steps instead of
  continuous streaming. The state machine already models each step discretely, so this is a
  config/timing change, not a redesign.
