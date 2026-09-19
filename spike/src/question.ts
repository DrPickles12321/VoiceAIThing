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
// OUTRO state). Actually generating/sending the gait-checker link is being built separately
// in that project's own repo -- this is a spoken line only, not a real link-delivery step.
export const OUTRO_TEXT =
  "Thank you so much for your time today. We'll send you a link shortly to complete a quick " +
  "recording for the gait tracker.";

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
