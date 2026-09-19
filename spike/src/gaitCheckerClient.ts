import { env } from "./env.js";
import type { MappedAnswer } from "./claudeMapper.js";
import type { PromQuestion } from "./question.js";

// See docs/architecture.md's "Integration contract with the gait checker" -- the link is a
// deterministic URL from the patient's code (no API call needed to generate it), separate
// from the survey submission below.
export function buildPatientLink(patientCode: string): string {
  return `${env.GAIT_CHECKER_BASE_URL}/patient/${encodeURIComponent(patientCode)}`;
}

export interface AnsweredQuestion {
  question: PromQuestion;
  mapped: MappedAnswer;
}

// POSTs the call's survey answers plus a walkthrough-completion flag to the gait checker's
// backend, once, after the call ends. Field names reflect the current handoff spec from that
// teammate's repo, not a finalized/versioned API -- confirm before relying on them elsewhere.
export async function submitSurvey(
  patientCode: string,
  answers: AnsweredQuestion[],
  walkthroughCompleted: boolean,
): Promise<{ ok: boolean }> {
  const surveyResponses: Record<string, number | string> = {};
  for (const { question, mapped } of answers) {
    const label = question.answerOptions.find((o) => o.code === mapped.mapped_value)?.label;
    surveyResponses[question.code] = label ?? mapped.mapped_value;
  }

  const url = `${env.GAIT_CHECKER_BASE_URL}/api/submit-survey`;
  const body = {
    patient_id: patientCode,
    timestamp: new Date().toISOString(),
    walkthrough_completed: walkthroughCompleted,
    survey_responses: surveyResponses,
  };

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      console.error(`[gait-checker] submit-survey failed: ${res.status} ${await res.text()}`);
      return { ok: false };
    }
    console.log("[gait-checker] survey submitted", body);
    return { ok: true };
  } catch (err) {
    // Per docs/architecture.md: the patient already has their link by this point, so a
    // failure here shouldn't block or retry -- just flag it and move on.
    console.error("[gait-checker] submit-survey request failed", err);
    return { ok: false };
  }
}
