import express from "express";
import { WebSocketServer, type WebSocket } from "ws";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { createClient, LiveTranscriptionEvents } from "@deepgram/sdk";
import { env } from "./env.js";
import {
  DOCTOR_INTRO_TEXT,
  OUTRO_TEXT,
  SMS_LINK_CONFIRMATION_TEXT,
  SPIKE_QUESTION,
  WALKTHROUGH_CLOSING_TEXT,
  WALKTHROUGH_COUNTDOWN_TEXT,
  WALKTHROUGH_GUIDANCE_TEXT,
} from "./question.js";
import { mapAnswer, type MappedAnswer } from "./claudeMapper.js";
import { synthesizeLinear16, TTS_SAMPLE_RATE } from "./deepgramTts.js";
import { buildPatientLink, submitSurvey } from "./gaitCheckerClient.js";
import { sendLinkSms } from "./smsSender.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const app = express();
app.use(express.static(path.join(__dirname, "..", "public")));

const deepgram = createClient(env.DEEPGRAM_API_KEY);

// --- Browser mic <-> Deepgram <-> Claude bridge: the spike's call flow --------------

type CallState =
  | "AWAITING_START"
  | "DOCTOR_INTRO"
  | "PLAYING_QUESTION"
  | "LISTENING"
  | "MAPPING"
  | "PLAYING_CONFIRMATION"
  | "OUTRO"
  | "SEND_SMS_LINK"
  | "WALKTHROUGH_GUIDANCE"
  | "WALKTHROUGH_COUNTDOWN"
  | "WALKTHROUGH_OBSERVE"
  | "DONE";

// Waits this long after the patient stops talking before assuming they're done --
// deliberately generous (see docs/architecture.md's turn-taking tuning) since
// orthopedic and stroke patients alike may need more time than a snappy default gives.
const ENDPOINTING_MS = 3500;
const UTTERANCE_END_MS = 4000;
const SILENCE_BACKSTOP_MS = 4500;

// How long to silently "watch" the patient walk before the closing line -- the voice side has
// no visibility into the gait checker's own camera feed, so this is just a timed pause (see
// docs/architecture.md's WALKTHROUGH_OBSERVE state).
const WALKTHROUGH_OBSERVE_MS = 5000;

const httpServer = createServer(app);
const wss = new WebSocketServer({ server: httpServer, path: "/media" });

function sendJson(ws: WebSocket, payload: unknown) {
  ws.send(JSON.stringify(payload));
}

// Sends a spoken line to the browser: a JSON preamble naming the line (so the client
// can report back when it's done playing) followed by the raw PCM16 audio itself.
async function speak(ws: WebSocket, text: string, markName: string) {
  const audio = await synthesizeLinear16(text);
  sendJson(ws, { type: "audio_start", markName, sampleRate: TTS_SAMPLE_RATE });
  ws.send(audio);
}

wss.on("connection", (ws: WebSocket) => {
  console.log("[media] browser connected");

  let state: CallState = "AWAITING_START";
  let micSampleRate = 16000;
  let finalTranscript = "";
  let silenceTimer: NodeJS.Timeout | null = null;
  let dgLive: ReturnType<typeof deepgram.listen.live> | null = null;
  let lastMappedAnswer: MappedAnswer | null = null;

  function resetSilenceBackstop() {
    if (silenceTimer) clearTimeout(silenceTimer);
    silenceTimer = setTimeout(() => {
      if (state === "LISTENING") finishListening();
    }, SILENCE_BACKSTOP_MS);
  }

  async function finishListening() {
    if (state !== "LISTENING") return;
    if (silenceTimer) clearTimeout(silenceTimer);
    state = "MAPPING";
    sendJson(ws, { type: "state", state });
    console.log(`[flow] patient said: "${finalTranscript}"`);

    if (!finalTranscript.trim()) {
      console.log("[flow] empty transcript, ending spike call");
      state = "DONE";
      sendJson(ws, { type: "state", state });
      ws.close();
      return;
    }

    try {
      const mapped = await mapAnswer(SPIKE_QUESTION, finalTranscript);
      lastMappedAnswer = mapped;
      console.log("[flow] Claude mapping:", mapped);
      sendJson(ws, { type: "mapping", ...mapped });

      state = "PLAYING_CONFIRMATION";
      sendJson(ws, { type: "state", state });
      await speak(ws, mapped.patient_facing_confirmation, "confirmation-done");
    } catch (err) {
      console.error("[flow] mapping/confirmation failed", err);
      sendJson(ws, { type: "error", text: String(err) });
      state = "DONE";
      ws.close();
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
        finalTranscript = `${finalTranscript} ${alt.transcript}`.trim();
        console.log(`[stt] final chunk: "${alt.transcript}"`);
        sendJson(ws, { type: "transcript", text: finalTranscript });
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
        await speak(ws, DOCTOR_INTRO_TEXT, "intro-done");
        break;
      }

      case "playback_done": {
        if (msg.markName === "intro-done") {
          state = "PLAYING_QUESTION";
          sendJson(ws, { type: "state", state });
          await speak(ws, SPIKE_QUESTION.promptText, "question-done");
        } else if (msg.markName === "question-done") {
          console.log("[flow] question finished playing, now listening");
          state = "LISTENING";
          sendJson(ws, { type: "state", state });
          resetSilenceBackstop();
        } else if (msg.markName === "confirmation-done") {
          // In the full 6-question build this only fires after the last question; the
          // spike has just one, so it always goes straight to the closing script.
          console.log("[flow] confirmation played, playing closing script");
          state = "OUTRO";
          sendJson(ws, { type: "state", state });
          await speak(ws, OUTRO_TEXT, "outro-done");
        } else if (msg.markName === "outro-done") {
          console.log("[flow] thank-you played, texting the gait-checker link");
          state = "SEND_SMS_LINK";
          sendJson(ws, { type: "state", state });
          const link = buildPatientLink(env.PATIENT_CODE);
          const { sent } = await sendLinkSms(link);
          sendJson(ws, { type: "gait_link", url: link, sent_via_sms: sent });
          await speak(ws, SMS_LINK_CONFIRMATION_TEXT, "sms-link-done");
        } else if (msg.markName === "sms-link-done") {
          console.log("[flow] staying on the line, giving walkthrough guidance");
          state = "WALKTHROUGH_GUIDANCE";
          sendJson(ws, { type: "state", state });
          await speak(ws, WALKTHROUGH_GUIDANCE_TEXT, "guidance-done");
        } else if (msg.markName === "guidance-done") {
          state = "WALKTHROUGH_COUNTDOWN";
          sendJson(ws, { type: "state", state });
          await speak(ws, WALKTHROUGH_COUNTDOWN_TEXT, "countdown-done");
        } else if (msg.markName === "countdown-done") {
          console.log(`[flow] observing for ${WALKTHROUGH_OBSERVE_MS}ms before closing`);
          state = "WALKTHROUGH_OBSERVE";
          sendJson(ws, { type: "state", state });
          setTimeout(async () => {
            if (state !== "WALKTHROUGH_OBSERVE") return; // connection may have closed already
            await speak(ws, WALKTHROUGH_CLOSING_TEXT, "closing-done");
          }, WALKTHROUGH_OBSERVE_MS);
        } else if (msg.markName === "closing-done") {
          console.log("[flow] call finished, submitting survey to the gait checker");
          const answers = lastMappedAnswer
            ? [{ question: SPIKE_QUESTION, mapped: lastMappedAnswer }]
            : [];
          const { ok } = await submitSurvey(env.PATIENT_CODE, answers, true);
          sendJson(ws, { type: "survey_submitted", ok });
          state = "DONE";
          sendJson(ws, { type: "state", state });
          ws.close();
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
