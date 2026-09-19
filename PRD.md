# PRD: AI Voice PROM Survey Caller

## 1. Problem

Orthopedic (and other) clinics rely on patient-reported outcome measures (PROMs) to:
- Establish a pre-operative baseline for how a patient is doing before treatment.
- Track long-term outcomes post-operatively — at ~3 months, 1 year, 5 years, and 10 years — both
  to check whether an individual patient needs follow-up care, and to power outcomes research
  comparing the efficacy of different procedures across patient demographics.

Today this data collection is broken in practice:
- **In-person collection** is done by clinically trained staff whose time is expensive and
  better spent on care than on transcribing survey answers (and whose handwriting can be
  illegible).
- **Emailed surveys** have poor response rates, especially for a procedure done years ago.
- **Phone-based collection** is done by staff calling patients one by one — slow, expensive,
  and doesn't scale across a clinic's full patient panel.

## 2. Goal

Build an AI system that places outbound phone calls to patients, conducts a standardized PROM
questionnaire conversationally, and outputs clean, structured survey data — without a human
having to run the call — while preserving the scientific validity of standardized survey
instruments.

## 3. Non-goals

- The AI is **not** a general chatbot. It must not free-chat, improvise new questions, or let
  the conversation wander — doing so would corrupt the standardized instrument the survey is
  built on.
- Not building EHR integration, patient scheduling, or billing in this phase.
- Not handling emergency/clinical-risk triage (e.g. detecting a medical emergency mid-call) —
  out of scope for the hackathon build, flagged as a future consideration.

## 4. Users

- **Clinic staff / coordinators**: trigger calls for a patient or cohort, review completed call
  transcripts and structured answers, and follow up on responses flagged for human review.
- **Patients**: receive a phone call, hear a doctor's voice (recorded or AI-cloned) explain the
  purpose, answer a fixed sequence of questions in their own words, and get a natural
  confirmation of how their answer was understood before moving on.
- **Researchers / clinic leadership** (downstream): consume the aggregated structured PROM data
  for outcomes studies comparing procedures/protocols across patient populations.

## 5. Core product requirements

1. **Outbound calling**: the system places a real phone call to a patient at a scheduled or
   on-demand time.
2. **Standardized question delivery**: the AI asks a fixed, ordered set of validated PROM
   questions (e.g. KOOS/HOOS-style knee/hip outcome questions) — the question wording and
   answer scale must not be improvised or altered.
3. **Natural free-text answer capture**: patients answer in their own words, at whatever length
   feels natural (including rambling), rather than being forced into a rigid response format.
4. **Answer-to-scale mapping**: an LLM maps the patient's free-text answer to the correct
   discrete point on that question's fixed answer scale.
5. **Confirmation loop**: before recording a final answer, the system states back its
   interpretation in natural language ("So it sounds like your knee pain has been moderate —
   is that right?") and only proceeds once confirmed, or asks a bounded number of targeted
   clarifying questions if the answer was ambiguous.
6. **Human-review fallback**: if an answer can't be confidently mapped after clarification
   attempts are exhausted, it's flagged for human review rather than guessed.
7. **Data capture**: every call's full transcript and every question's structured answer
   (raw text, mapped value, confidence, confirmation status) is persisted for later review and
   research use.
8. **Clinic-facing review**: a minimal dashboard to trigger calls and review completed call
   transcripts/structured answers.
9. **Opt-out**: patients should be able to opt out of AI-conducted calls in favor of a human
   follow-up (design consideration for the full product; not required for the hackathon demo).

## 6. Success criteria (hackathon demo)

- A real phone call is placed and completed end-to-end with no human in the loop.
- At least one full PROM domain (pain, stiffness, function, or quality of life) is covered by
  multiple questions asked, answered naturally, mapped, and confirmed correctly.
- A rambling, realistic answer (not just a clean one-word response) is correctly mapped to the
  intended scale value in front of judges.
- Completed call data (transcript + structured answers) is visible in a dashboard immediately
  after the call.

## 7. Success criteria (longer-term / post-hackathon)

- Measurable reduction in staff time spent per PROM collection cycle.
- Response/completion rate comparable to or better than emailed surveys.
- Structured data quality (agreement rate with a human-conducted call on the same patient) high
  enough to be usable in outcomes research without manual cleanup.
- Positive patient sentiment about the call experience (natural, respectful of their time, not
  robotic).

## 8. Key risks

- **Data integrity risk**: if the AI is allowed to free-chat or drift, collected data is no
  longer comparable to a standardized instrument. Mitigated by forcing structured tool-use
  output for every mapping decision (see `docs/architecture.md`) — the AI's spoken words are
  always chosen by the server, not generated ad hoc by the model mid-conversation.
- **Technical risk**: real-time telephony audio (Twilio Media Streams, mulaw/8kHz) combined
  with streaming STT/TTS is failure-prone; see `docs/architecture.md` for the fallback to a
  turn-based (non-streaming) pipeline if needed.
- **Elderly/rambling speech risk**: standard voice-endpointing defaults may cut patients off
  mid-thought; requires generous, tuned silence thresholds.
- **Trust/consent risk**: patients need to know they're talking to an AI and be able to opt for
  a human alternative (design requirement for production, not the hackathon demo).

## 9. Scope for this hackathon (HackMIT)

See `docs/architecture.md` for the technical plan and `spike/README.md` for the current Phase 0
feasibility spike status. In scope for the 24-hour build: one full survey (KOOS/HOOS-styled
knee/hip PROM, ~8 questions), a working outbound call flow, Supabase-backed storage, and a
minimal review dashboard. Out of scope: multi-survey support, scheduling/automation of when
calls go out, opt-out flows, EHR integration, and clinical risk triage.
