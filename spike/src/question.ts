// Single hardcoded PROM question for the Phase 0 spike.
// The full build seeds a whole bank of these from survey/koos-hoos-subset.json instead.

export interface AnswerOption {
  code: number;
  label: string;
}

export interface PromQuestion {
  code: string;
  promptText: string;
  answerOptions: AnswerOption[];
}

export const SPIKE_QUESTION: PromQuestion = {
  code: "KOOS_PAIN_1",
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
