# CLAUDE.md

This repository is intentionally staged and should not be treated as a single all-in-one production rewrite.

## Current state

The supported runtime is the safe core under `app/`:

- `app/models.py` defines the patient, question, and answer schema
- `app/patient_repository.py` performs strict patient lookup
- `app/question_loader.py` selects question banks by condition
- `app/survey_engine.py` manages the bounded confirmation flow
- `app/persistence.py` stores call metadata in the in-memory fallback layer
- `app/voice_adapter.py` defines the voice interaction contract
- `app/gait_handoff.py` prepares the downstream handoff payload without real delivery
- `app/telephony/` carries the survey over a real phone call: Twilio transport, Deepgram streaming speech-to-text and speech synthesis, and `PhoneCallSession`, which runs the turn loop without knowing either provider
- `phone_app.py` serves the operator dialer, the Twilio webhooks, and the media-stream websocket

The older `survey_intelligence/` module is retained as reference/demo code only. Do not treat it as the active implementation path.

## Safety principles

- Never guess a condition when a patient code is missing
- Require explicit confirmation before accepting an answer
- Stop after a bounded number of clarification retries and escalate for human review
- Keep external integrations behind failure-tolerant wrappers
- Separate demo behavior from production behavior

## Working rules for future changes

1. Keep the runtime layered: patient lookup, survey flow, persistence, voice, handoff.
2. Prefer small, reviewable slices over large monolithic rewrites.
3. Add tests for every new guardrail or state transition.
4. If a provider integration is added, isolate it behind a thin adapter.
5. Do not silently invent patient metadata or branch selection.

## Validation

Use the repo test suite as the baseline:

```bash
. .venv/bin/activate
python -m pytest -q
```
