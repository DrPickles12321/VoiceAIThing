# Survey intelligence

Python 3.10+. The demo uses all six HOOS, JR. HIP SURVEY items from the supplied
image in their original order. Definitions are in `survey_intelligence/surveys.py`.
Spoken prompts combine each section stem with its item: two hip-pain questions
and four physical-function questions, all referring to the last week. Choices
are None, Mild, Moderate, Severe, and Extreme. Instructions are adapted from
ticking boxes to spoken answers. No clinical score or interval conversion is implemented.

## Setup and run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create `.env` locally using `.env.example` as a template. Set `OPENAI_API_KEY`
to your API key and optionally `OPENAI_MODEL` (default: `gpt-4.1-mini`).
Keep the key on the backend; do not paste it into chat or commit it. `.env` is ignored.

```bash
python chat_demo.py             # Uses OpenAI; incurs API charges
python chat_demo.py --offline   # Limited keyword demonstration
python demo.py                  # Original scripted offline demonstration
python -m pytest -m 'not live'  # No API calls
RUN_LIVE_LLM_TESTS=1 python -m pytest -m live  # Seven paid synthetic evaluations
```

## Backend / voice handoff

```python
from survey_intelligence.surveys import HOOS_JR
from survey_intelligence.openai_extractor import OpenAIExtractor
from survey_intelligence.service import SurveyService

service = SurveyService(HOOS_JR, OpenAIExtractor())
first = service.create_session()
turn = service.handle_turn(first['session_id'], 'My difficulty is severe')
confirmed = service.handle_turn(first['session_id'], 'Yes')
```

Each result has `session_id`, `prompt`, `state`, `current_question`, `responses`,
and `safety_flags`. Speak `prompt` verbatim. Send complete finalized transcripts,
including confirmation replies, to the same method. Do not let a voice agent
independently choose questions, rewrite responses, or call `confirm('yes')` based
on its own interpretation. Rejecting a candidate requests a fresh answer.
Mixed confirmations such as "yes, actually no" remain unconfirmed.

This is an in-process service, not an HTTP server. Your backend teammate can wrap
it in authenticated FastAPI routes. Methods are synchronous: use a thread worker
from async code. Per-session locks serialize turns within one process. Session
storage is in memory and disappears on restart. Multiworker deployments need
transactional shared storage; transport retries need event IDs/idempotency.

## Model contract and guardrails

The OpenAI Responses API receives only the current question, its allowed options,
and the current transcript. A strict JSON schema limits candidate values and
fields. Instructions cover negation, corrections, unrelated answers, ambiguity,
and treating transcript instructions as untrusted data. No tools are offered.
The model cannot advance or persist anything. `store=False` disables response
storage; this does not promise zero retention by the provider.

Python independently checks question ID, allowed value, clarification flag, and
that evidence is a nonempty verbatim substring of the transcript. These checks
do not prove semantic correctness. Explicit confirmation is always required.
LLM results use `confidence=None`; model-generated numbers are not calibrated
probabilities. Legacy extractor confidence is validated if supplied.

API errors, refusals, incomplete output, malformed JSON and invalid candidates
leave the current question unanswered. SDK requests use a 10-second timeout and
at most one retry. Programming errors propagate after returning to clarification.

Phrase-based safety checks apply to answers AND confirmations. Matches clear
pending candidates and end the session in `escalated`. Exact opt-out phrases
(e.g. "stop", "stop the survey", "opt out") end it in `stopped`. Ended sessions
cannot restart. Escalation flags do not notify a real clinician; the backend must
implement and acknowledge that delivery before promising notification.

Phrase matching is a demo policy: it can miss paraphrases and flag negated or
historical statements. It is not a clinical triage system. Use synthetic data
for this prototype. Replace the policy and integrate actual review delivery
before clinical use.

Confirmed records separately preserve original `raw_response`, exact `evidence`,
and `confirmation_transcript`. Both candidates and confirmation state are owned
by the engine, not by callers.

## Evaluation and extensions

Offline tests verify state/provenance invariants and mock SDK failure cases.
They do not measure model understanding. The opt-in live suite checks rambling,
negation, correction, ambiguity, unrelated questions and prompt injection with
synthetic statements. Review failures before switching the configurable model.

Another provider can implement the same `(transcript, question) -> Extraction`
callable, raising `ExtractionError` on expected failures. Meta is not wired yet.
No database, telephony, survey scoring or HTTP deployment is included.

API references: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
and [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini).
