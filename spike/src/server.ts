import express from "express";
import { WebSocketServer, type WebSocket } from "ws";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { createClient, LiveTranscriptionEvents } from "@deepgram/sdk";
import { env } from "./env.js";
import {
  DOCTOR_INTRO_TEXT,
  MAX_CLARIFICATION_ATTEMPTS,
  OUTRO_TEXT,
  SMS_LINK_CONFIRMATION_TEXT,
  WALKTHROUGH_CLOSING_TEXT,
  WALKTHROUGH_COUNTDOWN_TEXT,
  WALKTHROUGH_GUIDANCE_TEXT,
  type PromQuestion,
} from "./question.js";
import { classifyConfirmation, mapAnswer, type MappedAnswer } from "./claudeMapper.js";
import { synthesizeLinear16, TTS_SAMPLE_RATE } from "./deepgramTts.js";
import { buildPatientLink, submitSurvey } from "./gaitCheckerClient.js";
import { sendLinkSms } from "./smsSender.js";
import { lookupPatient, type PatientRecord } from "./conditionLookup.js";
import { getQuestionSet } from "./questionSets.js";
import { supabase } from "./db/supabaseClient.js";
import { registerDashboardApi } from "./dashboardApi.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const app = express();
app.use(express.static(path.join(__dirname, "..", "public")));
registerDashboardApi(app);

const deepgram = createClient(env.DEEPGRAM_API_KEY);

// --- Browser mic <-> Deepgram <-> Claude bridge: the spike's call flow --------------

type CallState =
  | "AWAITING_START"
  | "DOCTOR_INTRO"
  | "LOOKUP_CONDITION"
  | "ASK_QUESTION"
  | "LISTENING"
  | "MAPPING"
  | "PLAYING_CONFIRMATION"
  | "CLARIFYING"
  | "OUTRO"
  | "SEND_SMS_LINK"
  | "WALKTHROUGH_GUIDANCE"
  | "WALKTHROUGH_COUNTDOWN"
  | "WALKTHROUGH_OBSERVE"
  | "PERSIST"
  | "DONE";

// What the current LISTENING phase is for: capturing an answer to the current question, or
// capturing a yes/no reply to the spoken confirmation. Determines what finishListening() does
// with the transcript once silence is detected.
type ListeningPurpose = "answer" | "confirm";

interface RecordedAnswer {
  question: PromQuestion;
  mapped: MappedAnswer;
  confirmedByPatient: boolean;
  clarificationAttempts: number;
  needsHumanReview: boolean;
}

interface TranscriptEntry {
  speaker: "ai" | "patient";
  text: string;
  ts: string;
}

// Waits this long after the patient stops talking before assuming they're done --
// deliberately generous (see docs/architecture.md's turn-taking tuning) since
// orthopedic and stroke patients alike may need more time than a snappy default gives.
const ENDPOINTING_MS = 3500;
const UTTERANCE_END_MS = 4000;
const SILENCE_BACKSTOP_MS = 4500;

// How long to silently "watch" the patient walk before the closing line -- the voice side has
// no visibility into the gait checker's own camera feed, so this is just a timed pause (see
// docs/architecture.md's WALKTHROUGH_OBSERVE state -- this is blind timing, not adaptive).
const WALKTHROUGH_OBSERVE_MS = 5000;

const httpServer = createServer(app);
const wss = new WebSocketServer({ server: httpServer, path: "/media" });

function sendJson(ws: WebSocket, payload: unknown) {
  ws.send(JSON.stringify(payload));
}

wss.on("connection", (ws: WebSocket) => {
  console.log("[media] browser connected");

  let state: CallState = "AWAITING_START";
  let micSampleRate = 16000;
  let questionTranscript = "";
  let silenceTimer: NodeJS.Timeout | null = null;
  let dgLive: ReturnType<typeof deepgram.listen.live> | null = null;

  let patient: PatientRecord | null = null;
  let callId: string | null = null;
  let questionSet: PromQuestion[] = [];
  let questionIndex = 0;
  let clarificationAttempts = 0;
  let currentMapped: MappedAnswer | null = null;
  let listeningPurpose: ListeningPurpose = "answer";
  const answers: RecordedAnswer[] = [];
  const fullTranscript: TranscriptEntry[] = [];
  let codeToQuestionId: Record<string, string> = {};

  // Sends a spoken line to the browser: a JSON preamble naming the line (so the client can
  // report back when it's done playing) followed by the raw PCM16 audio itself. Also logs the
  // line into this call's transcript.
  async function speak(text: string, markName: string) {
    fullTranscript.push({ speaker: "ai", text, ts: new Date().toISOString() });
    const audio = await synthesizeLinear16(text);
    sendJson(ws, { type: "audio_start", markName, sampleRate: TTS_SAMPLE_RATE });
    ws.send(audio);
  }

  function resetSilenceBackstop() {
    if (silenceTimer) clearTimeout(silenceTimer);
    silenceTimer = setTimeout(() => {
      if (state === "LISTENING") finishListening();
    }, SILENCE_BACKSTOP_MS);
  }

  async function askQuestion(i: number) {
    state = "ASK_QUESTION";
    sendJson(ws, { type: "state", state, questionIndex: i });
    questionTranscript = "";
    await speak(questionSet[i].promptText, "question-done");
  }

  async function advanceToNextQuestionOrOutro() {
    questionIndex += 1;
    clarificationAttempts = 0;
    if (questionIndex < questionSet.length) {
      await askQuestion(questionIndex);
    } else {
      state = "OUTRO";
      sendJson(ws, { type: "state", state });
      await speak(OUTRO_TEXT, "outro-done");
    }
  }

  function recordAnswer(opts: {
    confirmedByPatient: boolean;
    needsHumanReview: boolean;
  }) {
    if (!currentMapped) return;
    answers.push({
      question: questionSet[questionIndex],
      mapped: currentMapped,
      confirmedByPatient: opts.confirmedByPatient,
      clarificationAttempts,
      needsHumanReview: opts.needsHumanReview,
    });
    console.log(
      `[flow] recorded answer for ${questionSet[questionIndex].code}: ` +
        `${currentMapped.mapped_value} (confirmed=${opts.confirmedByPatient}, ` +
        `needs_human_review=${opts.needsHumanReview})`,
    );
    currentMapped = null;
  }

  async function askClarifyingQuestion(text: string) {
    clarificationAttempts += 1;
    state = "CLARIFYING";
    sendJson(ws, { type: "state", state, attempt: clarificationAttempts });
    questionTranscript = "";
    await speak(text, "clarification-done");
  }

  async function handleAnswerMapping() {
    const question = questionSet[questionIndex];
    console.log(`[flow] patient said (answer): "${questionTranscript}"`);

    if (!questionTranscript.trim()) {
      console.log("[flow] empty transcript, treating as unclear and re-asking");
      if (clarificationAttempts < MAX_CLARIFICATION_ATTEMPTS) {
        await askClarifyingQuestion(
          `Sorry, I didn't catch that. Could you tell me about your ${question.topic}?`,
        );
      } else {
        currentMapped = {
          mapped_value: -1,
          confidence: 0,
          needs_clarification: true,
          patient_facing_confirmation: "",
        };
        recordAnswer({ confirmedByPatient: false, needsHumanReview: true });
        await advanceToNextQuestionOrOutro();
      }
      return;
    }

    try {
      const mapped = await mapAnswer(question, questionTranscript);
      console.log("[flow] Claude mapping:", mapped);
      sendJson(ws, { type: "mapping", ...mapped });
      currentMapped = mapped;

      if (mapped.needs_clarification) {
        if (clarificationAttempts < MAX_CLARIFICATION_ATTEMPTS) {
          await askClarifyingQuestion(mapped.patient_facing_confirmation);
        } else {
          recordAnswer({ confirmedByPatient: false, needsHumanReview: true });
          await advanceToNextQuestionOrOutro();
        }
        return;
      }

      state = "PLAYING_CONFIRMATION";
      sendJson(ws, { type: "state", state });
      await speak(mapped.patient_facing_confirmation, "confirmation-done");
    } catch (err) {
      console.error("[flow] mapping failed", err);
      sendJson(ws, { type: "error", text: String(err) });
      state = "DONE";
      ws.close();
    }
  }

  async function handleConfirmationClassification() {
    console.log(`[flow] patient said (confirmation reply): "${questionTranscript}"`);
    try {
      const classification = questionTranscript.trim()
        ? await classifyConfirmation(questionTranscript)
        : { confirmed: false };
      console.log("[flow] confirmation classification:", classification);

      if (classification.confirmed) {
        recordAnswer({ confirmedByPatient: true, needsHumanReview: false });
        await advanceToNextQuestionOrOutro();
        return;
      }

      if (clarificationAttempts < MAX_CLARIFICATION_ATTEMPTS) {
        const question = questionSet[questionIndex];
        await askClarifyingQuestion(
          `No problem, let's try that again. Could you tell me more about your ${question.topic}?`,
        );
      } else {
        recordAnswer({ confirmedByPatient: false, needsHumanReview: true });
        await advanceToNextQuestionOrOutro();
      }
    } catch (err) {
      console.error("[flow] confirmation classification failed", err);
      sendJson(ws, { type: "error", text: String(err) });
      state = "DONE";
      ws.close();
    }
  }

  async function finishListening() {
    if (state !== "LISTENING") return;
    if (silenceTimer) clearTimeout(silenceTimer);
    state = "MAPPING";
    sendJson(ws, { type: "state", state });

    if (listeningPurpose === "answer") {
      await handleAnswerMapping();
    } else {
      await handleConfirmationClassification();
    }
  }

  function openDeepgramStt() {
    dgLive = deepgram.listen.live({
      model: "nova-2",
      encoding: "linear16",
      sample_rate: micSampleRate,
      channels: 1,
      smart_format: true,
      interim_results: true,
      endpointing: ENDPOINTING_MS,
      utterance_end_ms: UTTERANCE_END_MS,
    });

    dgLive.on(LiveTranscriptionEvents.Open, () => {
      console.log("[deepgram] STT socket open");
    });

    dgLive.on(LiveTranscriptionEvents.Transcript, (data) => {
      const alt = data.channel?.alternatives?.[0];
      if (!alt?.transcript) return;
      if (data.is_final) {
        questionTranscript = `${questionTranscript} ${alt.transcript}`.trim();
        fullTranscript.push({
          speaker: "patient",
          text: alt.transcript,
          ts: new Date().toISOString(),
        });
        console.log(`[stt] final chunk: "${alt.transcript}"`);
        sendJson(ws, { type: "transcript", text: questionTranscript });
        resetSilenceBackstop();
      } else {
        console.log(`[stt] interim: "${alt.transcript}"`);
      }
    });

    dgLive.on(LiveTranscriptionEvents.UtteranceEnd, () => {
      console.log("[deepgram] UtteranceEnd");
      if (state === "LISTENING") finishListening();
    });

    dgLive.on(LiveTranscriptionEvents.Error, (err) => {
      console.error("[deepgram] STT error", err);
      sendJson(ws, { type: "error", text: String(err) });
    });
  }

  async function runLookupCondition() {
    state = "LOOKUP_CONDITION";
    sendJson(ws, { type: "state", state });

    try {
      patient = await lookupPatient(env.PATIENT_CODE);
      questionSet = getQuestionSet(patient.conditionCategory);
      console.log(
        `[flow] patient ${patient.patientCode} is ${patient.conditionCategory} -- ` +
          `asking ${questionSet.length} questions`,
      );

      const questionSetCode =
        patient.conditionCategory === "orthopedic" ? "HOOS_JR_V1_HIP" : "STROKE_SUBSET_V1";
      const { data: seededQuestions, error: seedErr } = await supabase
        .from("survey_questions")
        .select("id, code")
        .eq("question_set_code", questionSetCode);
      if (seedErr) {
        console.error("[db] could not load survey_questions ids", seedErr);
      } else {
        codeToQuestionId = Object.fromEntries(
          (seededQuestions ?? []).map((q) => [q.code, q.id]),
        );
      }

      const { data: callRow, error: callErr } = await supabase
        .from("calls")
        .insert({ patient_id: patient.id, status: "in_progress", started_at: new Date().toISOString() })
        .select("id")
        .single();
      if (callErr || !callRow) {
        console.error("[db] could not create calls row", callErr);
      } else {
        callId = callRow.id;
      }

      sendJson(ws, {
        type: "condition",
        conditionCategory: patient.conditionCategory,
        questionCount: questionSet.length,
      });
      await askQuestion(0);
    } catch (err) {
      console.error("[flow] LOOKUP_CONDITION failed", err);
      sendJson(ws, { type: "error", text: String(err) });
      state = "DONE";
      ws.close();
    }
  }

  async function persistAndFinish() {
    state = "PERSIST";
    sendJson(ws, { type: "state", state });

    if (callId) {
      for (const a of answers) {
        const { error } = await supabase.from("call_responses").insert({
          call_id: callId,
          question_id: codeToQuestionId[a.question.code] ?? null,
          raw_patient_text: null,
          mapped_value_code: a.mapped.mapped_value,
          mapped_value_label:
            a.question.answerOptions.find((o) => o.code === a.mapped.mapped_value)?.label ?? null,
          llm_confidence: a.mapped.confidence,
          confirmed_by_patient: a.confirmedByPatient,
          clarification_attempts: a.clarificationAttempts,
          needs_human_review: a.needsHumanReview,
        });
        if (error) console.error("[db] call_responses insert failed", error);
      }

      const { error: updateErr } = await supabase
        .from("calls")
        .update({
          status: "completed",
          ended_at: new Date().toISOString(),
          full_transcript: fullTranscript,
        })
        .eq("id", callId);
      if (updateErr) console.error("[db] calls update failed", updateErr);
    } else {
      console.error("[db] no callId -- skipping call_responses/calls persistence");
    }

    const patientCode = patient?.patientCode ?? env.PATIENT_CODE;
    const link = buildPatientLink(patientCode);
    const { ok: submitOk } = await submitSurvey(
      patientCode,
      answers.map((a) => ({ question: a.question, mapped: a.mapped })),
      true,
    );

    if (callId) {
      const { error } = await supabase.from("gait_check_links").insert({
        call_id: callId,
        url: link,
        submitted_survey_data: submitOk,
        status: submitOk ? "sent" : "submit_failed",
      });
      if (error) console.error("[db] gait_check_links insert failed", error);
    }

    sendJson(ws, { type: "survey_submitted", ok: submitOk });
    state = "DONE";
    sendJson(ws, { type: "state", state });
    ws.close();
  }

  ws.on("message", async (raw, isBinary) => {
    if (isBinary) {
      if (state === "LISTENING" && dgLive) {
        const buf = raw as Buffer;
        dgLive.send(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
      }
      return; // strict turn-taking, no barge-in in the spike
    }

    const msg = JSON.parse(raw.toString());

    switch (msg.type) {
      case "start": {
        micSampleRate = msg.sampleRate;
        console.log(`[media] call started, mic sample rate ${micSampleRate}Hz`);
        openDeepgramStt();

        state = "DOCTOR_INTRO";
        sendJson(ws, { type: "state", state });
        await speak(DOCTOR_INTRO_TEXT, "intro-done");
        break;
      }

      case "playback_done": {
        if (msg.markName === "intro-done") {
          await runLookupCondition();
        } else if (msg.markName === "question-done" || msg.markName === "clarification-done") {
          console.log("[flow] prompt finished playing, now listening for an answer");
          state = "LISTENING";
          listeningPurpose = "answer";
          resetSilenceBackstop();
        } else if (msg.markName === "confirmation-done") {
          console.log("[flow] confirmation played, now listening for yes/no");
          state = "LISTENING";
          listeningPurpose = "confirm";
          questionTranscript = "";
          resetSilenceBackstop();
        } else if (msg.markName === "outro-done") {
          console.log("[flow] thank-you played, texting the gait-checker link");
          state = "SEND_SMS_LINK";
          sendJson(ws, { type: "state", state });
          const patientCode = patient?.patientCode ?? env.PATIENT_CODE;
          const link = buildPatientLink(patientCode);
          const { sent } = await sendLinkSms(link);
          sendJson(ws, { type: "gait_link", url: link, sent_via_sms: sent });
          await speak(SMS_LINK_CONFIRMATION_TEXT, "sms-link-done");
        } else if (msg.markName === "sms-link-done") {
          console.log("[flow] staying on the line, giving walkthrough guidance");
          state = "WALKTHROUGH_GUIDANCE";
          sendJson(ws, { type: "state", state });
          await speak(WALKTHROUGH_GUIDANCE_TEXT, "guidance-done");
        } else if (msg.markName === "guidance-done") {
          state = "WALKTHROUGH_COUNTDOWN";
          sendJson(ws, { type: "state", state });
          await speak(WALKTHROUGH_COUNTDOWN_TEXT, "countdown-done");
        } else if (msg.markName === "countdown-done") {
          console.log(`[flow] observing for ${WALKTHROUGH_OBSERVE_MS}ms before closing`);
          state = "WALKTHROUGH_OBSERVE";
          sendJson(ws, { type: "state", state });
          setTimeout(async () => {
            if (state !== "WALKTHROUGH_OBSERVE") return; // connection may have closed already
            await speak(WALKTHROUGH_CLOSING_TEXT, "closing-done");
          }, WALKTHROUGH_OBSERVE_MS);
        } else if (msg.markName === "closing-done") {
          console.log("[flow] call finished, persisting and submitting to the gait checker");
          await persistAndFinish();
        }
        break;
      }
    }
  });

  ws.on("close", () => {
    console.log("[media] browser disconnected");
    if (silenceTimer) clearTimeout(silenceTimer);
    dgLive?.requestClose();
  });
});

httpServer.listen(env.PORT, () => {
  console.log(`Spike server listening on http://localhost:${env.PORT}`);
  console.log("Open that URL in a browser and click Start to place the spike call.");
});
