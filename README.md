# VoiceAIThing

An AI-powered phone-call system that automates patient-reported outcome (PROM) survey
collection for orthopedic clinics — calling patients pre- and post-op, asking standardized
questions, and using an LLM to map their free-text (often rambling) answers to structured
survey codes, confirming each one back before moving on so the collected data stays clean.

Built for HackMIT (Healthcare / Deepgram / Regeneron tracks).

## Status

Currently in **Phase 0: feasibility spike** — see [`spike/`](./spike) for a small, throwaway
proof of concept that places one real phone call through Twilio, streams audio through
Deepgram STT/TTS, and uses Claude (forced tool-use) to map a rambling answer to a fixed
survey scale and confirm it back in natural language. See [`spike/README.md`](./spike/README.md)
for how to run it.

The full build plan (architecture, data model, 24h build order) lives in the project's
planning notes and will be fleshed out into `docs/architecture.md` once the spike validates
the approach.
