# CLAUDE.md

Guidance for Claude Code sessions working in this repository.

## What this project is

An AI phone-call system that automates patient-reported outcome (PROM) survey collection for
orthopedic clinics. Read `PRD.md` for the product context and `docs/architecture.md` for the
technical design before making non-trivial changes — both were written deliberately and reflect
real product/technical decisions, not placeholders.

## Repo layout

- `spike/` — a throwaway Phase 0 feasibility spike (Twilio + Deepgram STT/TTS + Claude
  tool-use, one hardcoded question, no persistence). This is intentionally minimal; don't add
  production concerns (retries, multi-question loops, a database) to it. If/when the spike is
  validated, its modules seed the equivalents under `packages/server/src/` per
  `docs/architecture.md`'s target repo structure — do not just keep expanding `spike/` in
  place.
- `docs/architecture.md` — system design: call transport, state machine, data model, repo
  structure, risks/fallbacks. Keep it in sync with real implementation decisions as the build
  progresses; don't let it drift into aspirational fiction.
- `PRD.md` — product requirements. Update it if scope changes materially (e.g. a new survey
  type, a new track requirement), don't just silently build around it.

## Non-negotiable design constraint

**The AI must never free-chat with patients.** Every point where the system decides what to
say back to a patient about their survey answer must go through a forced structured
tool-use call to Claude (`tool_choice` pinning a specific tool, e.g. `map_answer`), not an
open-ended prompt. This is what keeps collected survey data comparable to a standardized
instrument. Do not "simplify" this into a freeform chat completion, even to save time — it
would defeat the actual point of the project. See `spike/src/claudeMapper.ts` for the current
pattern.

## Environment limitations to know about

- Twilio and Deepgram's APIs (`api.twilio.com`, `api.deepgram.com`) are **not reachable** from
  Claude Code's sandboxed remote execution environment — the network policy blocks them. There
  is also no way to expose a public HTTPS/WSS URL for Twilio's webhooks from inside the
  sandbox. This means **live phone calls cannot be placed or tested from this environment.**
  When working on call-flow code here, write and typecheck it, but say plainly that live
  testing needs to happen locally (or another host with real network access) — don't claim a
  call was tested if it wasn't actually placed.
- `npm install` against `registry.npmjs.org` and calls to `api.anthropic.com` do work from this
  environment.

## Conventions

- Node/TypeScript, ESM (`"type": "module"` + `NodeNext` module resolution) — match this in any
  new package rather than mixing CJS.
- Audio format: Twilio Media Streams and Deepgram STT/TTS are both configured for raw
  mu-law/8kHz with no container, so audio can be piped through **without transcoding**. If you
  touch audio-handling code, preserve this — don't introduce a resampling/transcoding step
  unless there's a concrete reason.
- Prefer editing existing files under `spike/src/` or `packages/server/src/` (once created)
  over writing new one-off scripts elsewhere in the repo.
- Keep `spike/README.md` accurate to whatever the spike currently does — it's the run-book for
  a human to actually place a test call.

## Hackathon context

This is a HackMIT project targeting the Healthcare, Deepgram, and Regeneron tracks (see
`PRD.md` §9 and `docs/architecture.md`'s "Track fit" framing in the original plan). The repo is
MIT-licensed and intended to be genuinely open-source per Regeneron's judging criteria — don't
add closed/proprietary dependencies or license-incompatible code without flagging it.
