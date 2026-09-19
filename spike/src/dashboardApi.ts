import type { Express } from "express";
import { supabase } from "./db/supabaseClient.js";

// Minimal read-only review API backing public/dashboard.html -- lists completed (and
// in-progress) calls and shows one call's transcript + structured answers. Internal QA/review
// only, per docs/architecture.md -- distinct from the gait checker's own doctor-facing
// unified clinical report.
export function registerDashboardApi(app: Express) {
  app.get("/api/calls", async (_req, res) => {
    const { data, error } = await supabase
      .from("calls")
      .select("id, call_type, status, started_at, ended_at, patients(patient_code, full_name, condition_category)")
      .order("started_at", { ascending: false });

    if (error) {
      console.error("[dashboard] failed to list calls", error);
      res.status(500).json({ error: error.message });
      return;
    }
    res.json(data);
  });

  app.get("/api/calls/:id", async (req, res) => {
    const { id } = req.params;

    const { data: call, error: callErr } = await supabase
      .from("calls")
      .select("id, call_type, status, started_at, ended_at, full_transcript, patients(patient_code, full_name, condition_category)")
      .eq("id", id)
      .single();

    if (callErr || !call) {
      res.status(404).json({ error: callErr?.message ?? "call not found" });
      return;
    }

    const { data: responses, error: responsesErr } = await supabase
      .from("call_responses")
      .select(
        "id, raw_patient_text, mapped_value_code, mapped_value_label, llm_confidence, " +
          "confirmed_by_patient, clarification_attempts, needs_human_review, " +
          "survey_questions(code, prompt_text, domain)",
      )
      .eq("call_id", id)
      .order("created_at", { ascending: true });

    if (responsesErr) {
      console.error("[dashboard] failed to load call_responses", responsesErr);
      res.status(500).json({ error: responsesErr.message });
      return;
    }

    res.json({ call, responses: responses ?? [] });
  });
}
