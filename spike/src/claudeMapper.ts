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

export interface ConfirmationClassification {
  confirmed: boolean;
}

// Classifies the patient's spoken reply to a "You said your X was Y, correct?" confirmation
// as yes/no. Same forced-tool-use pattern as mapAnswer -- the model can only return a boolean,
// never free-chat back to the patient.
export async function classifyConfirmation(
  patientReply: string,
): Promise<ConfirmationClassification> {
  const response = await anthropic.messages.create({
    model: env.ANTHROPIC_MODEL,
    max_tokens: 100,
    system:
      "You classify whether a patient's spoken reply confirms or rejects a yes/no question " +
      "asked of them. You never chat, you only call the classify_confirmation tool.",
    messages: [
      {
        role: "user",
        content:
          `The patient was asked to confirm a statement about their survey answer. ` +
          `Their reply (transcribed): "${patientReply}"\n\n` +
          "Did they confirm (yes) or reject (no) the statement?",
      },
    ],
    tool_choice: { type: "tool", name: "classify_confirmation" },
    tools: [
      {
        name: "classify_confirmation",
        description: "Record whether the patient confirmed or rejected the statement.",
        input_schema: {
          type: "object",
          properties: {
            confirmed: {
              type: "boolean",
              description: "true if the patient confirmed (e.g. 'yes', 'that's right'), false if they rejected it (e.g. 'no', 'that's not right').",
            },
          },
          required: ["confirmed"],
        },
      },
    ],
  });

  const toolUse = response.content.find((block) => block.type === "tool_use");
  if (!toolUse || toolUse.type !== "tool_use") {
    throw new Error("Claude did not return the forced classify_confirmation tool call.");
  }

  return toolUse.input as ConfirmationClassification;
}
