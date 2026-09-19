// One-time seed script -- run manually (`npx tsx scripts/seed.ts`) after setting up Supabase,
// before placing a real call. Not part of the server's runtime path.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { supabase } from "../src/db/supabaseClient.js";
import { env } from "../src/env.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SURVEY_DIR = path.join(__dirname, "..", "..", "survey");

interface QuestionSetFile {
  survey_code: string;
  questions: Array<{
    code: string;
    sequence_order: number;
    domain: string;
    prompt_text: string;
    answer_options: unknown;
  }>;
}

async function seedQuestionSet(filename: string) {
  const raw = readFileSync(path.join(SURVEY_DIR, filename), "utf-8");
  const parsed: QuestionSetFile = JSON.parse(raw);

  const rows = parsed.questions.map((q) => ({
    question_set_code: parsed.survey_code,
    code: q.code,
    sequence_order: q.sequence_order,
    domain: q.domain,
    prompt_text: q.prompt_text,
    answer_options: q.answer_options,
  }));

  const { error } = await supabase.from("survey_questions").upsert(rows, { onConflict: "code" });
  if (error) throw new Error(`seeding ${filename} failed: ${error.message}`);
  console.log(`[seed] upserted ${rows.length} questions from ${filename} (${parsed.survey_code})`);
}

async function seedPatients() {
  const rows = [
    {
      patient_code: env.PATIENT_CODE, // matches .env's default demo patient -- orthopedic branch
      full_name: "Demo Orthopedic Patient",
      phone_number: "+15555550100",
      condition_category: "orthopedic",
      procedure_type: "total_hip_arthroplasty",
      procedure_date: "2026-06-01",
    },
    {
      patient_code: "RGN-0500",
      full_name: "Demo Stroke Patient",
      phone_number: "+15555550200",
      condition_category: "stroke",
    },
  ];

  const { error } = await supabase.from("patients").upsert(rows, { onConflict: "patient_code" });
  if (error) throw new Error(`seeding patients failed: ${error.message}`);
  console.log(`[seed] upserted ${rows.length} demo patients`);
}

async function main() {
  await seedQuestionSet("hoos-jr-hip.json");
  await seedQuestionSet("stroke-subset.json");
  await seedPatients();
  console.log("[seed] done");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
