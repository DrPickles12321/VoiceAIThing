# PRD: AI Voice Check-In + Gait Check Pipeline

## 1. Problem

Clinics need standardized, longitudinal check-ins with two overlapping patient populations:
orthopedic post-surgical patients and stroke recovery patients. Both need:
- A pre-treatment baseline, and repeated post-treatment check-ins (e.g. 3mo/1yr/5yr/10yr for
  orthopedic recovery, or a comparable recurring cadence for stroke recovery) to track how the
  patient is doing and power outcomes research across patients and protocols.
- An honest read on **movement quality**, not just self-reported symptoms — fall risk, gait
  abnormalities, and balance issues are hard to assess from a phone conversation alone, for
  either population.

Today this is broken in practice:
- **In-person collection** is done by clinically trained staff whose time is expensive and
  better spent on care than on transcribing survey answers (and whose handwriting can be
  illegible).
- **Emailed surveys** have poor response rates, especially long after a procedure or event.
- **Phone-based collection** is done by staff calling patients one by one — slow, expensive,
  and doesn't scale across a clinic's full patient panel.
- **Symptom surveys alone miss movement problems.** A patient can self-report "mild" pain or
  stiffness while still walking in a way that signals a real fall risk; conversely, gait data
  alone has no context on how the patient is actually feeling. Neither signal by itself gives
  a doctor the full picture.

## 2. Goal

Build a two-stage pipeline: (1) an AI voice conversation that feels like an actual back-and-forth
talk, opens with a doctor introduction, and collects a standardized 6-question symptom check-in
— choosing the orthopedic or stroke question set based on the patient's existing record — while
guaranteeing the collected data stays comparable to a validated instrument; and (2) at the end of
that call, a handoff to a separate gait-checking system where the patient performs walking/movement
exercises, so both symptom and movement data reach the doctor from a single check-in.

## 3. Non-goals

- The AI is **not** a general chatbot. It must not free-chat, improvise new questions, or let
  the conversation wander — doing so would corrupt the standardized instrument the survey is
  built on. This constraint is non-negotiable regardless of how conversational the call sounds
  (see `CLAUDE.md`).
- This repo does **not** build or own the gait checker. That system already exists separately;
  this repo only generates and delivers the link to it and defines the shape of the handoff.
  Its internals (capture method, analysis, doctor-facing report) are out of scope here.
- Not building EHR integration, patient scheduling, or billing in this phase.
- Not handling real-time clinical risk triage during the call (e.g. detecting a medical
  emergency mid-conversation) — out of scope for the hackathon build, flagged as a future
  consideration.

## 4. Users

- **Clinic staff / coordinators**: trigger calls for a patient or cohort, review completed call
  transcripts and structured answers, and follow up on responses flagged for human review.
- **Patients**: either post-surgical orthopedic patients or stroke recovery patients. They have
  a conversation (browser-based for the hackathon demo; a real phone call is a later
  production concern) that opens with a doctor's introduction, answer a fixed set of questions
  relevant to their condition in their own words — at whatever pace they need, including long
  pauses — get a natural confirmation of how their answer was understood, and finish by
  receiving a link to a short gait/movement check.
- **Researchers / clinic leadership** (downstream): consume the aggregated structured data —
  both symptom answers and, once linked, gait results — for outcomes studies comparing
  procedures, protocols, and recovery trajectories across patient populations.

## 5. Core product requirements

1. **Conversational voice call**: for the hackathon, a browser/desktop mic conversation (not a
   real phone call — that's a later production concern) that sounds like an actual
   back-and-forth conversation rather than a rigid menu-driven IVR.
2. **Doctor introduction**: every call opens with a spoken introduction establishing who's
   calling and why, before any questions are asked.
3. **Condition-based question selection**: before asking anything, look up the patient's
   condition category (orthopedic vs. stroke) from the patient record, then ask that
   category's fixed 6-question set. The AI never mixes sets, never improvises which set to
   use, and never asks the patient to self-select.
4. **Natural free-text answer capture with generous turn-taking**: patients answer in their own
   words, at whatever length feels natural (including rambling). The system waits roughly
   3–4 seconds of silence before assuming the patient is finished, tuned longer than a typical
   voice-agent default to accommodate slower or effortful speech (relevant for both elderly
   orthopedic patients and stroke patients who may have speech effects).
5. **Answer-to-scale mapping**: an LLM (Claude, via forced tool-use — see `CLAUDE.md`) maps the
   patient's free-text answer to the correct discrete point on that question's fixed answer
   scale. This call can only return a structured mapping, never open-ended chat.
6. **Confirmation loop**: after every question, the system states back its interpretation
   using a consistent, standard template — *"You said your \<topic\> was \<answer\>, correct?"*
   — rather than varying the phrasing question to question, and only proceeds once confirmed,
   or asks a bounded number of targeted clarifying questions if the answer was ambiguous. The
   consistent template is deliberate: it's part of what makes the AI sound trustworthy rather
   than unpredictable, alongside the doctor introduction.
7. **Human-review fallback**: if an answer can't be confidently mapped after clarification
   attempts are exhausted, it's flagged for human review rather than guessed.
8. **Closing script and end-of-call gait-checker handoff**: after the last question is
   confirmed, the system closes with a short thank-you plus a spoken mention that a gait-checker
   link is coming (e.g. "Thank you so much for your time today. We'll send you a link shortly to
   complete a quick recording for the gait tracker."). Actually generating and delivering that
   link — scoped to the right exercise set for the patient's condition category — is being built
   separately in the external gait-checker's own repo; for now the call only speaks the line
   above, it doesn't yet produce or send a real link.
9. **Data capture**: every call's full transcript and every question's structured answer (raw
   text, mapped value, confidence, confirmation status) is persisted for later review and
   research use.
10. **Clinic-facing review**: a minimal dashboard to trigger calls and review completed call
    transcripts/structured answers, with room to show linked gait-checker results once that
    integration exists.
11. **Opt-out**: patients should be able to opt out of AI-conducted calls in favor of a human
    follow-up (design consideration for the full product; not required for the hackathon demo).

## 6. Success criteria (hackathon demo)

- A full conversational call is completed end-to-end in the browser, with no human running it.
- The call opens with a doctor introduction, then asks a 6-question set selected correctly
  based on the patient's condition category (demo both branches: one orthopedic patient, one
  stroke patient, getting different questions).
- At least one answer is given as a realistic, rambling response (not a clean one-word answer),
  including a deliberately long pause, and is still correctly mapped, confirmed, and handled
  gracefully by the longer turn-taking timeout.
- Every confirmation uses the standard template phrasing, and the call closes with the
  thank-you + gait-checker mention script (real link generation is out of scope for this repo's
  demo — see requirement 8).
- Completed call data (transcript + structured answers) is visible in a dashboard immediately
  after the call.

## 7. Success criteria (longer-term / post-hackathon)

- Measurable reduction in staff time spent per check-in cycle, across both patient populations.
- Response/completion rate comparable to or better than emailed surveys.
- Structured data quality (agreement rate with a human-conducted call on the same patient) high
  enough to be usable in outcomes research without manual cleanup.
- Positive patient sentiment about the call experience (natural, respectful of their time and
  pace, not robotic).
- Doctors get a combined view of self-reported symptoms and objective gait data from a single
  patient check-in, giving a fuller picture of recovery than either signal alone.

## 8. Key risks

- **Data integrity risk**: if the AI is allowed to free-chat or drift, collected data is no
  longer comparable to a standardized instrument. Mitigated by forcing structured tool-use
  output for every mapping decision (see `docs/architecture.md` and `CLAUDE.md`) — the AI's
  spoken words are always chosen by the server, not generated ad hoc by the model mid-call.
  This risk is unchanged by making the conversation sound more natural — the confirmation
  sentence can be warmer, but it's still server-selected, not freely generated.
- **Technical risk**: real-time browser audio capture/playback combined with streaming
  STT/TTS is failure-prone; see `docs/architecture.md` for the fallback to a turn-based
  (non-streaming) pipeline if needed.
- **Slower/effortful speech risk**: standard voice-agent endpointing defaults may cut patients
  off mid-thought; this is why turn-taking is tuned to a longer, deliberate 3–4 second silence
  threshold rather than a typical voice-agent default — relevant for elderly orthopedic
  patients and doubly so for stroke patients.
- **Integration-contract risk**: the voice call and the gait checker are two independently
  built systems. If the URL/query-param contract between them isn't agreed and kept minimal,
  the handoff breaks. Keep the contract to a simple link (patient/call identifiers + exercise
  set) to reduce coordination risk under hackathon time pressure — see
  `docs/architecture.md`'s integration-contract section.
- **Trust/consent risk**: patients need to know they're talking to an AI and be able to opt for
  a human alternative (design requirement for production, not the hackathon demo).

## 9. Scope for this hackathon (HackMIT)

Both the voice call system (this repo) and the gait checker (a separate repo/deployment) are
full-scope deliverables, built independently and meeting only at the link handoff. This repo's
scope is: the browser-based conversational voice call, condition-based question branching
between an orthopedic set and a stroke set, the confirmation/clarification loop, Supabase-backed
storage, a minimal review dashboard, and generating the gait-checker link at the end of the call.
Out of scope for this repo: the gait checker's own capture/analysis/reporting, receiving results
back from it (flagged as an open integration point until that contract is defined), scheduling
automation for when calls go out, opt-out flows, EHR integration, and clinical risk triage.
See `docs/architecture.md` for the technical plan and `spike/README.md` for the current Phase 0
feasibility spike status (note: the spike currently reflects the earlier Twilio phone-call
design and needs to be revisited for the browser-mic pivot before it's used as a base for the
full build).
