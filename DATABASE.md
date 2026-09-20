# Database schema

This file documents the **additive** Postgres/Supabase layer added for the
HackMIT prototype. The existing in-memory survey runtime is unchanged and
remains the default.

All rows described here are **synthetic/demo data**. They are not real
patients and this schema does **not** make the prototype HIPAA compliant.

## What was added

New SQL lives in `supabase/migrations/`:

1. `20260919120000_survey_longitudinal_core.sql` — tables, indexes, scoring
   functions, dashboard/audit views, RLS.
2. `20260919120100_survey_synthetic_seed.sql` — idempotent demo rows.

Python scoring that mirrors the SQL rule (confirmed answers only) lives in
`app/scoring.py`. It can score in-memory `SafeSurveyEngine` answers without a
database.

## How this maps to existing code

| Existing runtime concept | Database equivalent |
| --- | --- |
| `PatientRecord.patient_code` | `patients.display_id` |
| `PatientRecord.patient_id` | `patients.id` |
| `PatientRecord.condition_category` | `patients.condition_category` |
| `SurveyQuestion.id` | `survey_questions.question_key` |
| `SurveyQuestion.prompt` | `survey_questions.question_text` |
| `session.answers` (confirmed only) | `survey_responses.confirmed_value` |
| `session.pending_answer` | `survey_responses.ai_proposed_value` while `confirmation_status = pending` |
| `InMemoryPersistence` call record | `call_sessions` metadata (no audio) |

Names, dates of birth, and other extra identifiers were **not** added because
the current demo does not need them.

A separate “knee outcomes” instrument was **not** created. The app already
ships HOOS JR (hip) as the orthopedic bank; the seed reuses those six
questions instead of duplicating a KOOS-style table.

## Tables

- `patients` — synthetic patients; `is_synthetic` is constrained to true.
- `survey_templates` / `survey_questions` — instruments and item scoring maps.
- `survey_instances` — a patient’s scheduled or completed follow-up
  (`pre-op`, `3 months`, `1 year`, `5 years`, plus status
  `scheduled|in_progress|completed|needs_review|failed`).
- `call_sessions` — call metadata only. **No audio columns.**
- `survey_responses` — raw statement, AI proposal, confidence, confirmation,
  evidence, and confirmed value.
- `review_flags` — human-review markers. `clinical_concern` is a flag type,
  not a diagnosis.
- `audit_events` — workflow actions such as `survey_started`,
  `answer_proposed`, `answer_confirmed`, `answer_corrected`,
  `survey_completed`.

## Scoring

`public.score_survey_instance(instance_id)` and `app.scoring` both:

- read **`confirmed_value` only** for rows with
  `confirmation_status` in (`confirmed`, `corrected`)
- ignore `ai_proposed_value` completely
- return `NULL` / `None` if any required question is unanswered, unconfirmed,
  or has an unmapped label

`survey_instances.total_score` is refreshed by a trigger on
`survey_responses`. The stored number is a **prototype sum of item weights**
(`none=0` … `extreme=4`, HOOS JR range 0–24). It is **not** the official
HOOS, JR interval score.

## Dashboard and audit queries

```sql
SELECT
  patient_display_id,
  follow_up_label,
  survey_status,
  completed_at,
  total_score,
  review_flag_count
FROM public.clinician_dashboard
ORDER BY scheduled_for NULLS LAST, patient_display_id;
```

```sql
SELECT
  patient_display_id,
  follow_up_label,
  question_key,
  raw_patient_text,
  ai_proposed_value,
  ai_confidence,
  confirmed_value,
  confirmation_status,
  evidence_text
FROM public.survey_response_audit
ORDER BY patient_display_id, question_order;
```

Both views use `security_invoker = true`, so base-table RLS still applies.

## Seed data

Idempotent inserts (safe to re-run; they do not delete existing rows):

- patients `RGN-0417` (orthopedic), `RGN-0500` (stroke), `RGN-0600` (orthopedic)
- one HOOS JR demo template with the six existing orthopedic questions
- one **completed** 3-month survey for `RGN-0417` (confirmed-value total **7**;
  item 2 is a correction so `severe` was proposed and `moderate` was scored)
- one **scheduled** pre-op survey for `RGN-0600`

## How to run migrations

Do **not** reset the database or edit already-applied migration files.

Supabase (linked project or local CLI):

```bash
supabase db push
```

SQL editor: run the two files in timestamp order.

Local Postgres:

```bash
psql "$DATABASE_URL" -f supabase/migrations/20260919120000_survey_longitudinal_core.sql
psql "$DATABASE_URL" -f supabase/migrations/20260919120100_survey_synthetic_seed.sql
```

On vanilla Postgres, Supabase roles (`anon`, `authenticated`, `service_role`)
may be absent. The migration skips those grants/policies and still creates
tables. Enable equivalent roles before exposing the database.

## How the backend should connect

The FastAPI voice app still uses `InMemoryPatientRepository` and
`InMemoryPersistence`. When a server-side database client is added later:

- set `DATABASE_URL` **or** `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`
  in server environment only (see `.env.example`)
- never put the service-role key in `voice_web/`, `NEXT_PUBLIC_*`, or any
  browser bundle
- keep `PATIENT_REPOSITORY=in_memory` until persistence is intentionally
  switched

See [SECURITY.md](SECURITY.md) for RLS assumptions and production gaps.
