import Anthropic from "@anthropic-ai/sdk";
import { env } from "./env.js";
import type { PromQuestion } from "./question.js";

const anthropic = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY });

export interface MappedAnswer {
  mapped_value: number;
  confidence: number;
  needs_clarification: boolean;
  patient_facing_confirmation: string;
}

// Forces Claude to return a structured mapping instead of free-form chat, so
// the AI cannot drift off-survey. tool_choice pins the model to this one tool.
export async function mapAnswer(
  question: PromQuestion,
  patientTranscript: string,
): Promise<MappedAnswer> {
  const optionsList = question.answerOptions
    .map((o) => `${o.code} = ${o.label}`)
    .join(", ");

  const response = await anthropic.messages.create({
    model: env.ANTHROPIC_MODEL,
    max_tokens: 300,
    system:
      "You map a patient's spoken, possibly rambling answer to a fixed survey scale. " +
      "You never invent new answer options, never chat, and never ask about anything outside this one question. " +
      "You must call the map_answer tool exactly once.",
    messages: [
      {
        role: "user",
        content:
          `Question asked: "${question.promptText}"\n` +
          `Confirmation topic (use this exact phrase): "${question.topic}"\n` +
          `Fixed answer scale: ${optionsList}\n\n` +
          `Patient's spoken answer (transcribed): "${patientTranscript}"\n\n` +
          "Map this to the closest scale value.",
      },
    ],
    tool_choice: { type: "tool", name: "map_answer" },
    tools: [
      {
        name: "map_answer",
        description:
          "Record the structured survey answer mapped from the patient's free-text response.",
        input_schema: {
          type: "object",
          properties: {
            mapped_value: {
              type: "integer",
              description: `One of the fixed scale codes: ${optionsList}`,
            },
            confidence: {
              type: "number",
              description: "0-1 confidence that mapped_value correctly reflects the patient's answer.",
            },
            needs_clarification: {
              type: "boolean",
              description: "true if the answer was too ambiguous to confidently map.",
            },
            patient_facing_confirmation: {
              type: "string",
              description:
                "Always phrase this using the exact standard template: " +
                `"You said your ${question.topic} was <answer label>, correct?" -- filling in ` +
                "<answer label> with the matched scale option's label (e.g. \"You said your " +
                `${question.topic} was moderate, correct?"). Use this template every time, ` +
                "do not vary the wording. If needs_clarification is true, instead ask a short " +
                "targeted disambiguating question using only the scale's own labels.",
            },
          },
          required: [
            "mapped_value",
            "confidence",
            "needs_clarification",
            "patient_facing_confirmation",
          ],
        },
      },
    ],
  });

  const toolUse = response.content.find((block) => block.type === "tool_use");
  if (!toolUse || toolUse.type !== "tool_use") {
    throw new Error("Claude did not return the forced map_answer tool call.");
  }

  return toolUse.input as MappedAnswer;
}
