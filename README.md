# VoiceAIThing

This repository now contains a safer, staged survey runtime instead of the earlier ad hoc spoken-demo prototype.

## What is in this repo now

The active runtime is the `app/` package. It enforces:

- patient lookup by code before starting the survey
- strict condition-based question selection
- explicit answer confirmation with bounded retry limits
- persisted call metadata in the in-memory fallback layer
- a voice/handoff boundary that prepares a gait-checker payload without sending real external links

The first-release scope is intentionally narrow:

- orthopedic and stroke branches are supported
- HOOS JR is the default orthopedic instrument
- patient records are not guessed; missing codes fail loudly
- real telephony, real external delivery, and production database wiring remain out of scope

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

The safe core can be exercised directly from Python:

```python
from app.patient_repository import InMemoryPatientRepository
from app.survey_engine import SafeSurveyEngine

engine = SafeSurveyEngine(InMemoryPatientRepository(), "RGN-0417")
print(engine.start())
print(engine.handle_response("mild"))
print(engine.handle_response("yes"))
```

## Configuration

Copy `.env.example` to `.env` and set any local values you need. The safe runtime includes:

```env
PATIENT_CODE=RGN-0417
PATIENT_REPOSITORY=in_memory
```

Legacy OpenAI/demo values remain in the file for compatibility with the older `survey_intelligence` examples, but the safe runtime does not depend on them for the core behavior.

## Validation

```bash
. .venv/bin/activate
python -m pytest -q
```

The repo is intentionally designed as a staged, reviewable stack rather than a giant one-shot rewrite.

## Older project docs

The package formerly used a different prototype system under `survey_intelligence/` and `web_app.py`. Those files still exist as historical/demo code, but the safe runtime in `app/` is the path to keep for ongoing work.
