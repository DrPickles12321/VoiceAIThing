import type { WebSocket } from "ws";

const FRAME_BYTES = 160; // 20ms of mulaw @ 8kHz, 1 byte/sample

// Streams a raw mulaw buffer to Twilio as 20ms media frames, then sends a
// "mark" event so the caller can await onMark(name) to know playback finished.
export function sendMulawToTwilio(
  ws: WebSocket,
  streamSid: string,
  audio: Buffer,
  markName: string,
) {
  for (let offset = 0; offset < audio.length; offset += FRAME_BYTES) {
    const frame = audio.subarray(offset, offset + FRAME_BYTES);
    ws.send(
      JSON.stringify({
        event: "media",
        streamSid,
        media: { payload: frame.toString("base64") },
      }),
    );
  }
  ws.send(
    JSON.stringify({
      event: "mark",
      streamSid,
      mark: { name: markName },
    }),
  );
}
