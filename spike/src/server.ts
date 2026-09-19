import express from "express";
import { WebSocketServer, type WebSocket } from "ws";
import { createServer } from "node:http";
import twilio from "twilio";
import { createClient, LiveTranscriptionEvents } from "@deepgram/sdk";
import { env } from "./env.js";
import { SPIKE_QUESTION } from "./question.js";
import { mapAnswer } from "./claudeMapper.js";
import { synthesizeMulaw } from "./deepgramTts.js";
import { sendMulawToTwilio } from "./twilioAudio.js";

const app = express();
app.use(express.urlencoded({ extended: false }));
app.use(express.json());

const twilioClient = twilio(env.TWILIO_ACCOUNT_SID, env.TWILIO_AUTH_TOKEN);
const deepgram = createClient(env.DEEPGRAM_API_KEY);

// --- Trigger the spike call -------------------------------------------------

app.post("/call", async (_req, res) => {
  try {
    const call = await twilioClient.calls.create({
      to: env.TEST_DESTINATION_NUMBER,
      from: env.TWILIO_FROM_NUMBER,
      url: `${env.PUBLIC_BASE_URL}/twiml`,
    });
    console.log(`[call] started ${call.sid} -> ${env.TEST_DESTINATION_NUMBER}`);
    res.json({ callSid: call.sid });
  } catch (err) {
    console.error("[call] failed to start", err);
    res.status(500).json({ error: String(err) });
  }
});

app.post("/twiml", (_req, res) => {
  const wsUrl = env.PUBLIC_BASE_URL.replace(/^http/, "ws") + "/media";
  res.type("text/xml").send(
    `<?xml version="1.0" encoding="UTF-8"?>` +
      `<Response><Connect><Stream url="${wsUrl}" /></Connect></Response>`,
  );
});

// --- Media stream: the actual spike call flow -------------------------------

type CallState =
  | "AWAITING_START"
  | "PLAYING_INTRO"
  | "LISTENING"
  | "MAPPING"
  | "PLAYING_CONFIRMATION"
  | "DONE";

const httpServer = createServer(app);
const wss = new WebSocketServer({ server: httpServer, path: "/media" });

wss.on("connection", (ws: WebSocket) => {
  console.log("[media] Twilio connected");

  let state: CallState = "AWAITING_START";
  let streamSid = "";
  let finalTranscript = "";
  let silenceTimer: NodeJS.Timeout | null = null;

  const dgLive = deepgram.listen.live({
    model: "nova-2",
    encoding: "mulaw",
    sample_rate: 8000,
    channels: 1,
    smart_format: true,
    interim_results: true,
    endpointing: 800, // ms of silence Deepgram treats as end-of-speech
    utterance_end_ms: 1500, // extra backstop for rambling/elderly pauses
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
  });

  // Backstop in case Deepgram's own endpointing doesn't fire (belt + suspenders,
  // per the plan's note that elderly/rambling speech needs a generous timeout).
  function resetSilenceBackstop() {
    if (silenceTimer) clearTimeout(silenceTimer);
    silenceTimer = setTimeout(() => {
      if (state === "LISTENING") finishListening();
    }, 2500);
  }

  async function finishListening() {
    if (state !== "LISTENING") return;
    if (silenceTimer) clearTimeout(silenceTimer);
    state = "MAPPING";
    console.log(`[flow] patient said: "${finalTranscript}"`);

    if (!finalTranscript.trim()) {
      console.log("[flow] empty transcript, skipping mapping");
      state = "DONE";
      ws.close();
      return;
    }

    try {
      const mapped = await mapAnswer(SPIKE_QUESTION, finalTranscript);
      console.log("[flow] Claude mapping:", mapped);

      state = "PLAYING_CONFIRMATION";
      const audio = await synthesizeMulaw(mapped.patient_facing_confirmation);
      sendMulawToTwilio(ws, streamSid, audio, "confirmation-done");
    } catch (err) {
      console.error("[flow] mapping/confirmation failed", err);
      state = "DONE";
      ws.close();
    }
  }

  ws.on("message", async (raw) => {
    const msg = JSON.parse(raw.toString());

    switch (msg.event) {
      case "start": {
        streamSid = msg.start.streamSid;
        console.log(`[media] stream started ${streamSid}`);
        state = "PLAYING_INTRO";
        const audio = await synthesizeMulaw(SPIKE_QUESTION.promptText);
        sendMulawToTwilio(ws, streamSid, audio, "question-done");
        break;
      }

      case "media": {
        if (state !== "LISTENING") return; // strict turn-taking, no barge-in in the spike
        const audioBuf = Buffer.from(msg.media.payload, "base64");
        dgLive.send(audioBuf.buffer.slice(audioBuf.byteOffset, audioBuf.byteOffset + audioBuf.byteLength));
        break;
      }

      case "mark": {
        if (msg.mark.name === "question-done") {
          console.log("[flow] intro/question finished playing, now listening");
          state = "LISTENING";
          resetSilenceBackstop();
        } else if (msg.mark.name === "confirmation-done") {
          console.log("[flow] confirmation played, ending spike call");
          state = "DONE";
          ws.close();
        }
        break;
      }

      case "stop": {
        console.log("[media] stream stopped");
        dgLive.requestClose();
        break;
      }
    }
  });

  ws.on("close", () => {
    console.log("[media] Twilio disconnected");
    if (silenceTimer) clearTimeout(silenceTimer);
    dgLive.requestClose();
  });
});

httpServer.listen(env.PORT, () => {
  console.log(`Spike server listening on :${env.PORT}`);
  console.log(`POST ${env.PUBLIC_BASE_URL}/call to place the spike call`);
});
