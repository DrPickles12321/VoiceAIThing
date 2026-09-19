# CLAUDE.md

Guidance for Claude Code sessions working in this repository.

## What this project is

An AI voice conversation system that conducts a standardized 6-question symptom check-in with
orthopedic or stroke recovery patients (branching by condition), then hands the patient off to
a separate gait-checking system. Read `PRD.md` for the product context and
`docs/architecture.md` for the technical design before making non-trivial changes — both were
written deliberately and reflect real product/technical decisions, not placeholders.

**Pivot note**: the project originally used real Twilio phone calls; it has since pivoted to a
browser/desktop mic conversation for the hackathon demo (see `docs/architecture.md`). The gait
checker is a separate, already-built system in another repo — this repo only generates and
delivers a link to it, it does not implement the gait checker itself.

## Repo layout

- `spike/` — started as a throwaway Phase 0 feasibility spike but, by explicit request, now
  implements most of the full design: a static page (`spike/public/`) captures mic audio via
  an `AudioWorklet` and streams it to `spike/src/server.ts` over a WebSocket, which bridges to
  Deepgram STT/TTS and Claude; `conditionLookup.ts` + `questionSets.ts` branch between the real
  HOOS JR (orthopedic) and representative stroke question sets via a real Supabase `patients`
  lookup; the full per-question loop includes confirmation classification and bounded
  clarification retries; and `PERSIST` writes `calls`/`call_responses`/`gait_check_links` rows
  and submits to the gait checker; `dashboardApi.ts` + `public/dashboard.html` serve a basic
  internal review UI over the persisted calls. It is **no longer minimal** — this note replaces
  an earlier version of itself that said the opposite. `packages/server/` and
  `packages/dashboard/` (per `docs/architecture.md`'s target repo structure) still don't exist
  as separate packages; this functionality currently lives in `spike/`. What's still missing:
  any automation for triggering calls (still manual, one browser tab at a time).
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

- Deepgram's API (`api.deepgram.com`) is **not reachable** from Claude Code's sandboxed remote
  execution environment — the network policy blocks it. There is also no real microphone/audio
  device or browser to test the mic-capture pipeline against inside the sandbox. This means
  **a live voice conversation cannot be placed or tested from this environment**, browser-based
  or otherwise. When working on call-flow code here, write and typecheck it, but say plainly
  that live testing needs to happen locally (or another host with a real browser/mic and
  network access) — don't claim a conversation was tested if it wasn't actually run.
- `npm install` against `registry.npmjs.org` and calls to `api.anthropic.com` do work from this
  environment.
- Direct HTTP calls to Supabase's REST API (`*.supabase.co`) are also blocked (same network
  policy) — a script that calls `@supabase/supabase-js` directly (e.g. `spike/scripts/seed.ts`)
  can't run from here either. The **Supabase MCP tools** (`mcp__Supabase__*`) are a separate,
  allowed channel for schema/data operations (they don't go through the blocked network path) —
  use those for migrations, seeding, and verification queries instead of running scripts that
  hit the database directly.

## Conventions

- Node/TypeScript, ESM (`"type": "module"` + `NodeNext` module resolution) — match this in any
  new package rather than mixing CJS.
- Audio format: the browser mic capture pipeline and Deepgram STT/TTS must agree exactly on
  encoding and sample rate (see `docs/architecture.md`'s "Call transport" section) so audio can
  be piped through with minimal transcoding. If you touch audio-handling code, match whatever
  format the capture pipeline actually produces rather than assuming a fixed rate.
- Prefer editing existing files under `spike/src/` or `packages/server/src/` (once created)
  over writing new one-off scripts elsewhere in the repo.
- Keep `spike/README.md` accurate to whatever the spike currently does — it's the run-book for
  a human to actually place a test call.

## Hackathon context

This is a HackMIT project targeting the Healthcare, Deepgram, and Regeneron tracks (see
`PRD.md` §9 and `docs/architecture.md`'s "Track fit" framing in the original plan). The repo is
MIT-licensed and intended to be genuinely open-source per Regeneron's judging criteria — don't
add closed/proprietary dependencies or license-incompatible code without flagging it.
