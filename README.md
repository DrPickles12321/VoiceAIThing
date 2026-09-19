# VoiceAIThing

An AI voice conversation system that conducts a standardized symptom check-in with orthopedic
or stroke recovery patients — branching the question set by condition, sounding like a real
conversation rather than an IVR menu, and using an LLM to map free-text (often rambling)
answers to structured survey codes, confirming each one back before moving on so the collected
data stays clean. At the end of the call, the patient is handed off to a separate gait-checking
system for a walking/movement assessment.

Built for HackMIT (Healthcare / Deepgram / Regeneron tracks).

## Docs

- [`PRD.md`](./PRD.md) — problem, goals, requirements, success criteria, scope.
- [`docs/architecture.md`](./docs/architecture.md) — technical design: call transport, state
  machine, data model, question banks, gait-checker integration contract, risks and fallbacks.
- [`CLAUDE.md`](./CLAUDE.md) — guidance for AI coding agents (or humans) working in this repo,
  including the non-negotiable "never let the AI free-chat with patients" constraint and known
  environment limitations.
- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — setup and contribution notes.

## Status

The project pivoted from real Twilio phone calls to a **browser/desktop mic conversation** for
the hackathon demo, and split into two connected pieces: this repo (the voice call) and a
separate, already-built gait-checker system that this repo only links out to.

[`spike/`](./spike) is a Phase 0 feasibility spike that now runs entirely in a browser tab
(no phone, no Twilio, no ngrok) — mic capture, Deepgram STT/TTS, and Claude tool-use mapping,
for a doctor intro plus one hardcoded question. See [`spike/README.md`](./spike/README.md) to
run it.

The full build (browser-based state machine, condition-based question branching, Supabase
storage, review dashboard, gait-checker link handoff) follows the plan in
`docs/architecture.md`.

## License

MIT — see [`LICENSE`](./LICENSE).
