# Phase 0 Feasibility Spike (browser mic)

Throwaway code proving the riskiest part of the current design end-to-end, entirely in a
**browser tab on your own machine**: mic capture → Deepgram STT (live) → Claude forced tool-use
mapping → Deepgram TTS confirmation, for a doctor introduction plus one hardcoded orthopedic
PROM question. No database, no dashboard, no multi-question loop, no phone call — just: does
this round-trip work, and does it feel like a real conversation?

This previously used a real Twilio phone call; the project pivoted to a browser-mic demo (see
`docs/architecture.md`), which removes the need for a Twilio account, ngrok, or a public URL
entirely. Everything here runs on `localhost`.

## Setup

1. `cp .env.example .env` and fill in:
   - `DEEPGRAM_API_KEY` — from console.deepgram.com.
   - `ANTHROPIC_API_KEY` — your Claude API key.

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
   server's terminal output: live transcript, Claude's `map_answer` tool call result, the
   spoken confirmation ("You said your knee pain was \_\_\_, correct?" — always this exact
   template), and finally a closing thank-you that mentions a gait-checker link is coming
   before the call ends.

## What to judge

- **Conversational feel**: does the doctor intro + question + confirmation + closing sequence
  feel like an actual conversation, not a rigid menu?
- **Confirmation consistency**: does the confirmation always follow the "You said your \<topic\>
  was \<answer\>, correct?" template regardless of how the patient phrased their answer?
- **Turn-taking**: does the ~3–4 second pause tolerance feel right — long enough not to cut
  patients off mid-thought, but not so long the call feels unresponsive?
- **Audio quality**: did mic capture and TTS playback both come through cleanly (garbled or
  silent audio would point to a sample-rate mismatch between the browser and Deepgram)?
- **Mapping quality**: did Claude pick a sensible scale value from a rambling answer?
- **Latency**: was the pause between finishing speaking and hearing the confirmation tolerable?

Note: the closing line mentions a gait-checker link, but no real link is generated or sent yet
— that integration is being built separately (see `docs/architecture.md`'s "Integration
contract with the gait checker" and `PRD.md` requirement 8). This spike only speaks the line.

## How it works (for orientation)

- `public/index.html` + `public/client.js` + `public/pcm-worklet.js` — the browser side: mic
  capture via `getUserMedia` + an `AudioWorklet` that converts Float32 samples to Int16 PCM and
  posts them to the main thread, which streams them over a WebSocket; TTS audio comes back the
  same way and is scheduled for gapless playback via `AudioContext`.
- `src/server.ts` — the state machine: `DOCTOR_INTRO → PLAYING_QUESTION → LISTENING → MAPPING
  → PLAYING_CONFIRMATION → OUTRO → DONE`. Turn-taking is coordinated by the client reporting back
  `{type: "playback_done", markName}` once it's finished playing a given line, mirroring what
  Twilio's `mark` events did for the old telephony version.
- `src/integrations` equivalents: `src/deepgramTts.ts` (linear16 PCM synthesis) and
  `src/claudeMapper.ts` (forced `map_answer` tool-use — unchanged from before, see
  `CLAUDE.md`'s non-negotiable "never free-chat" constraint).

If this feels compelling, this code seeds `packages/server/src/{ws/browserStream.ts,
integrations/deepgramStt.ts, integrations/deepgramTts.ts, integrations/claudeMapper.ts,
call-flow/stateMachine.ts, call-flow/conditionLookup.ts}` in the full build (see
`docs/architecture.md`). If the streaming pipeline is too flaky to demo reliably, fall back to
a turn-based version (buffer a full utterance, then run STT → Claude → TTS as discrete steps)
instead of sinking more time into full-duplex streaming.
