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
separate, already-built gait-checker system (working name **GaitGuard**) that this repo submits
survey data to and links out to.

[`spike/`](./spike) started as a Phase 0 feasibility spike but now implements nearly the full
system: browser mic capture (no phone, no Twilio voice), the full 6-question loop branching
between the real **HOOS, JR.** hip instrument and a representative stroke set via a real
Supabase patient lookup, confirmation + bounded clarification retries, the full live
gait-checker handoff (SMS link, walkthrough guidance, Supabase persistence, survey submission),
and a basic internal review dashboard for past calls. See [`spike/README.md`](./spike/README.md)
to run it.

Still missing: any call-triggering automation — still one manual browser tab per call. See
`docs/architecture.md` and `CLAUDE.md` for exactly what's built vs. not.

## License

MIT — see [`LICENSE`](./LICENSE).
