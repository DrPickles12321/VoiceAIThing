// Single hardcoded PROM question for the Phase 0 spike, plus a doctor-introduction
// opener (see docs/architecture.md's DOCTOR_INTRO state). The full build looks up the
// patient's condition_category and asks a full 6-question set from
// survey/koos-hoos-subset.json or survey/stroke-subset.json instead.

export interface AnswerOption {
  code: number;
  label: string;
}

export interface PromQuestion {
  code: string;
  // Short phrase naming what's being confirmed, e.g. "knee pain" -- used to fill in the
  // standard confirmation template ("You said your <topic> was <answer>, correct?").
  topic: string;
  promptText: string;
  answerOptions: AnswerOption[];
}

export const DOCTOR_INTRO_TEXT =
  "Hi, this is Dr. Rivera's office calling to check in on how your knee has been doing. " +
  "I'm going to ask you a quick question about it -- take your time answering, there's no rush at all.";

// Closing script played after the last question is confirmed (see docs/architecture.md's
// OUTRO state). The call stays on the line after this -- see the SEND_SMS_LINK /
// WALKTHROUGH_* states below -- rather than hanging up right after the thank-you.
export const OUTRO_TEXT = "Thank you so much for your time today.";

// Spoken right after the gait-checker link is texted (or, if SMS isn't configured, right
// after it's logged as a fallback -- see docs/architecture.md's "New SMS dependency" risk).
export const SMS_LINK_CONFIRMATION_TEXT =
  "I've just texted you a secure link. Go ahead and open it on your phone or computer.";

// Live, step-by-step guidance for getting into position -- matches the visual cues the gait
// checker's own page shows (per the handoff spec). Fixed script, not model-generated: this is
// instructional, not a point where free-text patient answers need mapping.
export const WALKTHROUGH_GUIDANCE_TEXT =
  "Tap the 'Live Camera' mode, prop your device up against a stable surface where your full " +
  "body is visible, and step back a few paces.";

// Counts the patient into the walk. The "one... two... three" pacing is baked into the text
// itself (via pauses) rather than split into separate TTS calls, to keep this simple.
export const WALKTHROUGH_COUNTDOWN_TEXT =
  "When you're ready, I'll count to three, and you can walk slowly across the frame from " +
  "left to right. One... two... three... go ahead.";

// Played after a short observation pause (see docs/architecture.md's WALKTHROUGH_OBSERVE
// state) -- a warm, generic closing regardless of what actually happened during the walk,
// since the voice side has no visibility into the gait checker's own camera feed.
export const WALKTHROUGH_CLOSING_TEXT = "Great, thank you! Take care.";

export const SPIKE_QUESTION: PromQuestion = {
  code: "PAIN_1",
  topic: "knee pain",
  promptText:
    "Over the past week, how would you describe your knee pain during activities like walking or climbing stairs?",
  answerOptions: [
    { code: 0, label: "None" },
    { code: 1, label: "Mild" },
    { code: 2, label: "Moderate" },
    { code: 3, label: "Severe" },
    { code: 4, label: "Extreme" },
  ],
};
