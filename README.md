# VoiceAIThing

An AI-powered phone-call system that automates patient-reported outcome (PROM) survey
collection for orthopedic clinics — calling patients pre- and post-op, asking standardized
questions, and using an LLM to map their free-text (often rambling) answers to structured
survey codes, confirming each one back before moving on so the collected data stays clean.

Built for HackMIT (Healthcare / Deepgram / Regeneron tracks).

## Docs

- [`PRD.md`](./PRD.md) — problem, goals, requirements, success criteria, scope.
- [`docs/architecture.md`](./docs/architecture.md) — technical design: call transport, state
  machine, data model, repo structure, risks and fallbacks.
- [`CLAUDE.md`](./CLAUDE.md) — guidance for AI coding agents (or humans) working in this repo,
  including the non-negotiable "never let the AI free-chat with patients" constraint and known
  environment limitations.
- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — setup and contribution notes.

## Status

Currently in **Phase 0: feasibility spike** — see [`spike/`](./spike) for a small, throwaway
proof of concept that places one real phone call through Twilio, streams audio through
Deepgram STT/TTS, and uses Claude (forced tool-use) to map a rambling answer to a fixed
survey scale and confirm it back in natural language. See [`spike/README.md`](./spike/README.md)
for how to run it.

The full build (state machine, Supabase-backed storage, review dashboard) follows the plan in
`docs/architecture.md` once the spike validates the core approach on a real call.

## License

MIT — see [`LICENSE`](./LICENSE).
