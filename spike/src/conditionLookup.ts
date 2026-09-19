import { supabase } from "./db/supabaseClient.js";

export type ConditionCategory = "orthopedic" | "stroke";

export interface PatientRecord {
  id: string;
  patientCode: string;
  conditionCategory: ConditionCategory;
}

// LOOKUP_CONDITION (see docs/architecture.md) -- reads the patient's condition from their
// record rather than ever asking or improvising it. Fails loudly if the patient isn't found:
// the whole point of this step is that the question-set choice is never guessed.
export async function lookupPatient(patientCode: string): Promise<PatientRecord> {
  const { data, error } = await supabase
    .from("patients")
    .select("id, patient_code, condition_category")
    .eq("patient_code", patientCode)
    .single();

  if (error || !data) {
    throw new Error(
      `No patient found for patient_code "${patientCode}" -- run spike/scripts/seed.ts first. ` +
        (error?.message ?? ""),
    );
  }

  return {
    id: data.id,
    patientCode: data.patient_code,
    conditionCategory: data.condition_category as ConditionCategory,
  };
}
