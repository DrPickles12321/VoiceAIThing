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
guaranteeing the collected data stays comparable to a validated instrument; and (2) rather than
just handing off and disconnecting, the AI **stays on the line as a companion** through the
transition to a separate gait-checking system: it texts the patient their personalized link,
then walks them through getting into position and starting the walk, live, before ending the
call — so both symptom and movement data reach the doctor from a single, guided check-in.

## 3. Non-goals

- The AI is **not** a general chatbot. It must not free-chat, improvise new questions, or let
  the conversation wander — doing so would corrupt the standardized instrument the survey is
  built on. This constraint is non-negotiable regardless of how conversational the call sounds
  (see `CLAUDE.md`).
- This repo does **not** build or own the gait checker, its capture/analysis, or the
  doctor-facing unified clinical report — that teammate's system (working name **GaitGuard**)
  owns all of that, merging our submitted survey answers with its own gait telemetry into the
  clinician view. This repo's only responsibilities toward that system are submitting a call's
  survey answers to it and generating the patient's personalized link (see
  `docs/architecture.md`'s integration contract).
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
  pauses — get a natural confirmation of how their answer was understood, and then, rather than
  being dropped, are texted their personalized gait-check link and walked through getting set
  up and starting the walk while the AI stays on the line with them like a companion, not a
  system that hands them off and disappears.
- **Doctors / clinicians** (downstream, served by the gait-checker teammate's system, not this
  repo directly): view the unified clinical report — our submitted survey answers merged with
  gait telemetry and an AI-generated correlation summary — on the gait checker's doctor's
  portal.
- **Researchers / clinic leadership** (downstream): consume the aggregated structured data —
  both symptom answers and, once linked, gait results — for outcomes studies comparing
  procedures, protocols, and recovery trajectories across patient populations.

## 5. Core product requirements

1. **Conversational voice call**: for the hackathon, a browser/desktop mic conversation (not a
   real phone call — that's a later production concern) that sounds like a companion
   hand-holding the patient through the process, not a rigid menu-driven IVR — warm,
   back-and-forth, and willing to stay with the patient rather than drop them the moment the
   survey ends.
2. **Doctor introduction**: every call opens with a spoken introduction establishing who's
   calling and why, before any questions are asked.
3. **Condition-based question selection**: before asking anything, look up the patient's
   condition category (orthopedic vs. stroke) from the patient record, then ask that
   category's fixed 6-question set. The orthopedic set is the real, validated **HOOS, JR.**
   hip instrument (not a hackathon approximation — see `docs/architecture.md`'s question banks
   section); the stroke set is our own representative approximation until a real equivalent
   instrument is sourced. The AI never mixes sets, never improvises which set to use, and never
   asks the patient to self-select.
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
8. **Guided handoff to the gait checker — the call stays on the line**: after the last question
   is confirmed, the AI doesn't just say goodbye and hang up. It:
   1. Gives a short thank-you.
   2. Texts the patient their personalized gait-checker link
      (`https://<gait-checker-domain>/patient/<patient_code>`) and says so ("I've just texted
      you a secure link. Go ahead and open it on your phone or computer.").
   3. Stays on the line and gives live, step-by-step spoken instructions for getting into
      position — matching the visual cues the gait checker's own page shows (e.g. "Tap the
      'Live Camera' mode, prop your device up against a stable surface where your full body is
      visible, and step back a few paces.").
   4. Counts the patient into the walk ("When you're ready, I'll count to three, and you can
      walk slowly across the frame from left to right.") and waits briefly before a warm
      closing line and hanging up.
   5. Once the call ends, `POST`s the survey answers plus a `walkthrough_completed` flag to the
      gait checker's backend (`/api/submit-survey`) in one request — see
      `docs/architecture.md`'s integration contract for the exact payload/link shape and why
      the link-texting and data-submission steps happen at different points in the call.
   **Implemented in `spike/`** (see `spike/README.md`); the new SMS provider dependency this
   introduced falls back to a spoken/logged link if not configured, rather than failing the
   call.
9. **Data capture**: every call's full transcript and every question's structured answer (raw
   text, mapped value, confidence, confirmation status) is persisted for later review and
   research use.
10. **Clinic-facing review**: a minimal dashboard, owned by this repo, to trigger calls and
    review completed call transcripts/structured answers for internal QA/follow-up. This is
    distinct from the doctor-facing **unified clinical report**, which lives entirely on the
    gait checker's doctor's portal and merges our submitted survey data with their gait
    telemetry — this repo does not build or duplicate that merged view.
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
- Every confirmation uses the standard template phrasing, and after the last question the AI
  stays on the line — texts the link, walks the patient through camera setup, and counts them
  into the walk — rather than hanging up right after the survey (see requirement 8).
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
  built systems, and the `POST /api/submit-survey` payload shape + shared `patient_code` scheme
  reflect the teammate's current spec, not a finalized/versioned API. Confirm field names
  against their actual route before relying on them, and make the submission failure-tolerant
  (the patient already has their link by the time this `POST` fires, so a failure here shouldn't
  block or retry indefinitely) — see `docs/architecture.md`'s integration-contract section.
- **New SMS dependency**: texting the link mid-call needs a messaging provider and account setup
  that the browser-mic pivot otherwise avoided — budget setup time for it, and have a fallback
  (speak/display the URL without a real text) ready in case it's not wired up in time.
- **Trust/consent risk**: patients need to know they're talking to an AI and be able to opt for
  a human alternative (design requirement for production, not the hackathon demo).

## 9. Scope for this hackathon (HackMIT)

Both the voice call system (this repo) and the gait checker/doctor's-portal system (a separate
repo/deployment, working name **GaitGuard**) are full-scope deliverables, built independently
and meeting at a live handoff: this repo texts the patient their personalized link mid-call,
stays on the line to guide them into position for the walk, and submits survey answers plus a
completion flag once the call ends; their repo owns gait capture/analysis and the unified
doctor-facing clinical report entirely. This repo's scope is: the browser-based conversational
voice call, condition-based question branching between an orthopedic set and a stroke set, the
standardized confirmation template and closing/handoff script, the confirmation/clarification
loop, the live walkthrough guidance, Supabase-backed storage, a minimal internal review
dashboard, and the SMS link delivery + end-of-call survey submission. Out of scope for this
repo: the gait checker's own capture/analysis/reporting, the doctor's portal itself, receiving
anything back from that system (their backend is the merge point, not ours — see
`docs/architecture.md`'s integration contract), scheduling automation for when calls go out,
opt-out flows, EHR integration, and clinical risk triage.
See `docs/architecture.md` for the technical plan and `spike/README.md` for the current status
(the spike now implements nearly everything above — the browser-mic conversation, doctor
intro, condition branching via a real Supabase patient lookup, the full 6-question loop with
confirmation and bounded clarification retries, the closing thank-you, the full guided
gait-checker handoff, Supabase persistence, and a basic internal review dashboard. Still
missing: any call-triggering automation — still one manual browser tab per call).
