# Phase 0 Feasibility Spike

Throwaway code proving the riskiest part of the idea end-to-end on a **real phone call**:
Twilio call → Deepgram STT (live) → Claude forced tool-use mapping → Deepgram TTS confirmation,
for a single hardcoded orthopedic PROM question. No database, no dashboard, no multi-question
loop — just: does this round-trip work, and does it feel good?

This must be run somewhere with real outbound network access to `api.twilio.com` and
`api.deepgram.com`, and a public HTTPS/WSS URL Twilio can reach (a sandboxed CI/cloud dev
environment may block both). Locally with ngrok is the easy path.

## Setup

1. `cp .env.example .env` and fill in:
   - `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` — from the Twilio console.
   - `TWILIO_FROM_NUMBER` — a Twilio number you own.
   - `TEST_DESTINATION_NUMBER` — the phone you'll answer. **On a Twilio trial account this
     number must be verified in the console first**, or the call will be rejected.
   - `DEEPGRAM_API_KEY` — from console.deepgram.com.
   - `ANTHROPIC_API_KEY` — your Claude API key.
   - `PUBLIC_BASE_URL` — filled in after you start ngrok (step 3).

2. `npm install`

3. In one terminal: `npm run dev` (starts the server on `PORT`, default 3000).
   In another: `ngrok http 3000`, then copy the `https://...ngrok-free.app` URL into
   `PUBLIC_BASE_URL` in `.env` and restart the dev server so it picks up the new value.

4. Trigger the call:
   ```bash
   curl -X POST "$PUBLIC_BASE_URL/call"
   ```

5. Answer the phone. You should hear the question spoken, then have a chance to answer —
   try rambling the way an elderly patient might ("oh you know, some days it's fine, other
   days going up the stairs after gardening it really acts up..."). Watch the server logs:
   interim/final STT transcripts, Claude's `map_answer` tool call result, and finally the
   spoken confirmation before the call ends.

## What to judge

- **Format plumbing**: did audio flow cleanly both ways with no transcoding glitches
  (garbled/silent audio would indicate a mulaw/8kHz mismatch)?
- **Mapping quality**: did Claude pick a sensible scale value from a rambling answer, and
  did the confirmation sentence sound natural rather than robotic?
- **Latency**: was the pause between finishing speaking and hearing the confirmation
  tolerable on a live line?
- **Endpointing**: did the system wait long enough for pauses without cutting the patient
  off, but not so long that it felt unresponsive?

If this feels compelling, this code seeds `packages/server/src/{ws/mediaStream.ts,
integrations/deepgramStt.ts, integrations/deepgramTts.ts, integrations/claudeMapper.ts}`
in the full build (see `/docs` at the repo root for the full plan). If the streaming
pipeline is too flaky to demo reliably, fall back to a turn-based version instead of
sinking more time into full-duplex streaming.
