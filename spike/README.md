# Phase 0 Spike (browser mic) — now most of the full design

Started as a throwaway proof of concept; by explicit request it now implements nearly the
whole system end-to-end, entirely in a **browser tab on your own machine**: mic capture →
Deepgram STT (live) → Claude forced tool-use mapping → Deepgram TTS confirmation, for a doctor
introduction plus the **full 6-question loop**, branching between the real **HOOS, JR.** hip
survey and a representative stroke set based on a real Supabase patient lookup — with
confirmation classification and bounded clarification retries — and then, rather than hanging
up, a live gait-checker handoff where the AI stays on the line, texts the patient their link,
walks them through getting into position, and finally persists everything to Supabase. Still
missing: a real dashboard/review UI and any call-triggering automation (one browser tab, one
call, at a time).

This previously used a real Twilio phone call; the project pivoted to a browser-mic demo (see
`docs/architecture.md`), which removes the need for a Twilio *voice* account, ngrok, or a
public URL entirely. Everything here runs on `localhost`. (Twilio's SMS-only Messaging API is
optionally used again, just for the gait-checker link text.)

## Setup

1. `cp .env.example .env` and fill in:
   - `DEEPGRAM_API_KEY` — from console.deepgram.com.
   - `ANTHROPIC_API_KEY` — your Claude API key.
   - `SUPABASE_URL` / `SUPABASE_ANON_KEY` — already filled in with a real hackathon-only
     Supabase project (permissive RLS, no real patient data); leave as-is unless you're
     pointing at your own project.
   - `GAIT_CHECKER_BASE_URL` and `PATIENT_CODE` — leave the defaults if you don't have a real
     gait-checker deployment to point at yet; the spike will still run, the survey submission
     will just fail against a non-existent host (logged, not fatal). Set `PATIENT_CODE` to
     `RGN-0417` (orthopedic, HOOS JR questions) or `RGN-0500` (stroke, the representative set)
     to demo either branch — both are pre-seeded.
   - Optionally, `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_SMS_FROM_NUMBER` +
     `PATIENT_PHONE_NUMBER` to actually send a real text with the link. Leave them blank to use
     the spoken/logged fallback (no real SMS) — that's an expected, non-broken mode.

2. `npm install`

3. **Seed the database once** (only needed if you're using your own Supabase project instead
   of the shared hackathon one, or want to reset the demo data):
   `npx tsx scripts/seed.ts` — upserts both question sets into `survey_questions` and the two
   demo patients into `patients`.

4. `npm run dev` (starts the server on `PORT`, default 3000).

5. Open `http://localhost:3000` in a browser that has mic access (Chrome/Edge/Firefox all
   work; Safari's AudioWorklet support can be flakier). Click **Start call**, allow microphone
   access when prompted.

6. You'll hear a doctor-introduction line, then `LOOKUP_CONDITION` looks up `PATIENT_CODE` in
   Supabase and picks the matching question set. Then it asks all 6 questions in order,
   confirming each with the standard template ("You said your \<topic\> was \<answer\>,
   correct?") and actually listening for your yes/no reply — say "no" once to see the
   clarification retry loop (bounded to 2 attempts before it gives up and flags the answer for
   human review rather than looping forever). Try rambling on at least one answer ("oh you know,
   some days it's fine, other days going up the stairs after gardening it really acts up...")
   and **deliberately pause mid-sentence** to confirm the ~3–4 second silence tolerance doesn't
   cut you off. Watch the on-page log and the server's terminal output for live transcripts,
   each `map_answer`/`classify_confirmation` result, and state transitions.

7. After the 6th question's thank-you, the call **stays on the line**: it texts (or logs, if
   SMS isn't configured) the gait-checker link, tells you it did, walks you through camera
   setup, counts you into the walk, waits a few seconds, gives a closing line, and only then
   hangs up. On hangup it writes `call_responses` rows and updates the `calls` row in Supabase,
   then submits all 6 answers plus a `walkthrough_completed` flag to
   `<GAIT_CHECKER_BASE_URL>/api/submit-survey` and records a `gait_check_links` row. Watch the
   terminal for `[db]`, `[gait-checker]`, and `[sms]` log lines confirming each step.

## What to judge

- **Conversational feel**: does the doctor intro → 6 questions → thank-you → walkthrough
  sequence feel like a companion staying with you, not a rigid menu that drops you the moment
  the survey ends?
- **Condition branching**: does switching `PATIENT_CODE` between the two seeded demo patients
  actually change which 6 questions get asked?
- **Confirmation + clarification**: does the confirmation always follow the template, and does
  saying "no" trigger a real re-ask rather than being ignored?
- **Turn-taking**: does the ~3–4 second pause tolerance feel right?
- **Walkthrough pacing**: does staying on the line feel reassuring or does it drag? (See the
  honesty note in `docs/architecture.md`'s `WALKTHROUGH_OBSERVE` section — the current pause is
  a fixed timer, not an adaptive wait for the patient to actually be ready.)
- **Audio quality**: did mic capture and TTS playback come through cleanly across all 6
  questions, not just the first?
- **Persistence**: after a call, do the Supabase `calls`/`call_responses`/`gait_check_links`
  rows look right (query them directly, or ask whoever has the Supabase project open)?

## How it works (for orientation)

- `public/index.html` + `public/client.js` + `public/pcm-worklet.js` — the browser side: mic
  capture via `getUserMedia` + an `AudioWorklet` that converts Float32 samples to Int16 PCM and
  posts them to the main thread, which streams them over a WebSocket; TTS audio comes back the
  same way and is scheduled for gapless playback via `AudioContext`.
- `src/server.ts` — the full state machine: `DOCTOR_INTRO → LOOKUP_CONDITION → ASK_QUESTION →
  LISTENING → MAPPING → (CLARIFYING loop) → PLAYING_CONFIRMATION → LISTENING → OUTRO →
  SEND_SMS_LINK → WALKTHROUGH_GUIDANCE → WALKTHROUGH_COUNTDOWN → WALKTHROUGH_OBSERVE → PERSIST
  → DONE`, looping `ASK_QUESTION` through the confirmation step once per question. Turn-taking
  is coordinated by the client reporting back `{type: "playback_done", markName}`.
- `src/conditionLookup.ts` — `LOOKUP_CONDITION`: queries `patients` by `patient_code`, fails
  loudly (not a silent guess) if the patient isn't found.
- `src/questionSets.ts` — loads `survey/hoos-jr-hip.json` or `survey/stroke-subset.json` based
  on the looked-up condition.
- `src/claudeMapper.ts` — `mapAnswer` (forced `map_answer` tool-use, unchanged from before) and
  `classifyConfirmation` (forced `classify_confirmation` tool-use, new — classifies the
  patient's yes/no reply to the spoken confirmation).
- `src/db/supabaseClient.ts` + `scripts/seed.ts` — the Supabase client and the one-time seed
  script for `survey_questions` and demo `patients`.
- `src/gaitCheckerClient.ts` — builds the deterministic patient link and POSTs the final
  survey submission (see `docs/architecture.md`'s integration contract for why those are two
  separate calls at two different points in the flow).
- `src/smsSender.ts` — sends the link via Twilio's Messaging API if configured, otherwise logs
  it as a fallback.

If the streaming pipeline proves too flaky to demo reliably, fall back to a turn-based version
(buffer a full utterance, then run STT → Claude → TTS as discrete steps) instead of sinking
more time into full-duplex streaming.
