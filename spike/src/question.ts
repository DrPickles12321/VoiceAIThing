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
  promptText: string;
  answerOptions: AnswerOption[];
}

export const DOCTOR_INTRO_TEXT =
  "Hi, this is Dr. Rivera's office calling to check in on how your knee has been doing. " +
  "I'm going to ask you a quick question about it -- take your time answering, there's no rush at all.";

export const SPIKE_QUESTION: PromQuestion = {
  code: "PAIN_1",
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
