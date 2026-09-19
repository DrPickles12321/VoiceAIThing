import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import type { AnswerOption, PromQuestion } from "./question.js";
import type { ConditionCategory } from "./conditionLookup.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SURVEY_DIR = path.join(__dirname, "..", "..", "survey");

interface QuestionSetFile {
  survey_code: string;
  description: string;
  questions: Array<{
    code: string;
    sequence_order: number;
    domain: string;
    topic: string;
    prompt_text: string;
    answer_options: AnswerOption[];
  }>;
}

function loadFile(filename: string): PromQuestion[] {
  const raw = readFileSync(path.join(SURVEY_DIR, filename), "utf-8");
  const parsed: QuestionSetFile = JSON.parse(raw);
  return parsed.questions
    .sort((a, b) => a.sequence_order - b.sequence_order)
    .map((q) => ({
      code: q.code,
      topic: q.topic,
      promptText: q.prompt_text,
      answerOptions: q.answer_options,
    }));
}

// LOOKUP_CONDITION picks between these (see docs/architecture.md). Read directly from the
// bundled JSON rather than round-tripping through Supabase's survey_questions table at call
// time -- that table stays the source of truth for the schema/full build, seeded by
// spike/scripts/seed.ts, but the spike already has the wording locally.
export function getQuestionSet(condition: ConditionCategory): PromQuestion[] {
  switch (condition) {
    case "orthopedic":
      return loadFile("hoos-jr-hip.json");
    case "stroke":
      return loadFile("stroke-subset.json");
  }
}
