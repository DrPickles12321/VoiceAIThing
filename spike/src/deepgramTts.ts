import { env } from "./env.js";

// Deepgram TTS's supported linear16 output rates. 24000 is a safe default -- the
// browser's AudioContext will resample on playback regardless of its own sample rate.
export const TTS_SAMPLE_RATE = 24000;

// Requests raw linear16 PCM (no WAV/container header) directly from Deepgram's TTS REST
// endpoint so it can be decoded and played by the browser with minimal handling.
export async function synthesizeLinear16(text: string): Promise<Buffer> {
  const url = `https://api.deepgram.com/v1/speak?model=aura-2-thalia-en&encoding=linear16&sample_rate=${TTS_SAMPLE_RATE}&container=none`;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Token ${env.DEEPGRAM_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text }),
  });

  if (!res.ok) {
    throw new Error(`Deepgram TTS failed: ${res.status} ${await res.text()}`);
  }

  return Buffer.from(await res.arrayBuffer());
}
