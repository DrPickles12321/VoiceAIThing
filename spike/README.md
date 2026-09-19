# Phase 0 Feasibility Spike (browser mic)

Throwaway code proving the riskiest parts of the current design end-to-end, entirely in a
**browser tab on your own machine**: mic capture → Deepgram STT (live) → Claude forced tool-use
mapping → Deepgram TTS confirmation, for a doctor introduction plus one hardcoded orthopedic
PROM question — and then, rather than hanging up, a live gait-checker handoff where the AI
stays on the line, texts the patient their link, and walks them through getting into position.
No database, no dashboard, no multi-question loop, no phone call, no condition branching yet —
just: does this round-trip work, and does it feel like a real, attentive conversation?

This previously used a real Twilio phone call; the project pivoted to a browser-mic demo (see
`docs/architecture.md`), which removes the need for a Twilio *voice* account, ngrok, or a
public URL entirely. Everything here runs on `localhost`. (Twilio's SMS-only Messaging API is
now optionally used again, just for the gait-checker link text — see step 5 below.)

## Setup

1. `cp .env.example .env` and fill in:
   - `DEEPGRAM_API_KEY` — from console.deepgram.com.
   - `ANTHROPIC_API_KEY` — your Claude API key.
   - `GAIT_CHECKER_BASE_URL` and `PATIENT_CODE` — leave the defaults if you don't have a real
     gait-checker deployment to point at yet; the spike will still run, the survey submission
     will just fail against a non-existent host (logged, not fatal — see step 6).
   - Optionally, `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_SMS_FROM_NUMBER` +
     `PATIENT_PHONE_NUMBER` to actually send a real text with the link. Leave them blank to use
     the spoken/logged fallback (no real SMS) — that's an expected, non-broken mode.

2. `npm install`

3. `npm run dev` (starts the server on `PORT`, default 3000).

4. Open `http://localhost:3000` in a browser that has mic access (Chrome/Edge/Firefox all
   work; Safari's AudioWorklet support can be flakier). Click **Start call**, allow microphone
   access when prompted.

5. You'll hear a doctor-introduction line, then the question. Answer naturally — try
   rambling the way a real patient might ("oh you know, some days it's fine, other days going
   up the stairs after gardening it really acts up...") and **deliberately pause mid-sentence**
   to check that the system waits for you instead of cutting you off (it's tuned to wait
   roughly 3–4 seconds of silence before assuming you're done). Watch the on-page log and the
   server's terminal output: live transcript, Claude's `map_answer` tool call result, and the
   spoken confirmation ("You said your knee pain was \_\_\_, correct?" — always this exact
   template).

6. After the thank-you, the call **stays on the line** rather than ending: it texts (or logs,
   if SMS isn't configured) the gait-checker link, tells you it did, then walks you through
   camera setup ("Tap the 'Live Camera' mode, prop your device up...") and counts you into the
   walk, waits a few seconds, gives a closing line, and only then hangs up. Once the call ends,
   it submits the survey answer plus a `walkthrough_completed` flag to
   `<GAIT_CHECKER_BASE_URL>/api/submit-survey` — watch the terminal for `[gait-checker]` and
   `[sms]` log lines confirming what happened at each step.

## What to judge

- **Conversational feel**: does the doctor intro → question → confirmation → thank-you →
  walkthrough-guidance sequence feel like a companion staying with you, not a rigid menu that
  drops you the moment the survey ends?
- **Confirmation consistency**: does the confirmation always follow the "You said your \<topic\>
  was \<answer\>, correct?" template regardless of how the patient phrased their answer?
- **Turn-taking**: does the ~3–4 second pause tolerance feel right — long enough not to cut
  patients off mid-thought, but not so long the call feels unresponsive?
- **Walkthrough pacing**: does staying on the line after the survey feel reassuring or does it
  drag? Is the countdown/pause before the closing line timed reasonably
  (`WALKTHROUGH_OBSERVE_MS` in `src/server.ts`, currently 5 seconds)?
- **Audio quality**: did mic capture and TTS playback both come through cleanly (garbled or
  silent audio would point to a sample-rate mismatch between the browser and Deepgram)?
- **Mapping quality**: did Claude pick a sensible scale value from a rambling answer?
- **Latency**: was the pause between finishing speaking and hearing the confirmation tolerable?

## How it works (for orientation)

- `public/index.html` + `public/client.js` + `public/pcm-worklet.js` — the browser side: mic
  capture via `getUserMedia` + an `AudioWorklet` that converts Float32 samples to Int16 PCM and
  posts them to the main thread, which streams them over a WebSocket; TTS audio comes back the
  same way and is scheduled for gapless playback via `AudioContext`.
- `src/server.ts` — the state machine: `DOCTOR_INTRO → PLAYING_QUESTION → LISTENING → MAPPING
  → PLAYING_CONFIRMATION → OUTRO → SEND_SMS_LINK → WALKTHROUGH_GUIDANCE →
  WALKTHROUGH_COUNTDOWN → WALKTHROUGH_OBSERVE → DONE`. Turn-taking is coordinated by the client
  reporting back `{type: "playback_done", markName}` once it's finished playing a given line.
- `src/gaitCheckerClient.ts` — builds the deterministic patient link and POSTs the final
  survey submission (see `docs/architecture.md`'s integration contract for why those are two
  separate calls at two different points in the flow).
- `src/smsSender.ts` — sends the link via Twilio's Messaging API if configured, otherwise logs
  it as a fallback. This is a much lighter Twilio integration than the Voice/Media Streams
  product the project dropped in the browser-mic pivot — just one HTTP call, no audio.
- `src/deepgramTts.ts` (linear16 PCM synthesis) and `src/claudeMapper.ts` (forced `map_answer`
  tool-use — unchanged from before, see `CLAUDE.md`'s non-negotiable "never free-chat"
  constraint).

**Not yet implemented here**: condition-based branching (orthopedic vs. stroke), the full
6-question loop (still just one hardcoded question), and a real gait-checker backend to submit
to (the `POST` will fail against the default `.env.example` domain until you point
`GAIT_CHECKER_BASE_URL` at a real deployment — that failure is handled gracefully, not fatal).

If this feels compelling, this code seeds `packages/server/src/{ws/browserStream.ts,
integrations/deepgramStt.ts, integrations/deepgramTts.ts, integrations/claudeMapper.ts,
integrations/gaitCheckerClient.ts, integrations/smsSender.ts, call-flow/stateMachine.ts,
call-flow/conditionLookup.ts}` in the full build (see `docs/architecture.md`). If the streaming
pipeline is too flaky to demo reliably, fall back to a turn-based version (buffer a full
utterance, then run STT → Claude → TTS as discrete steps) instead of sinking more time into
full-duplex streaming.
