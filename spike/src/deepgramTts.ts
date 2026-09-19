import { env } from "./env.js";

// Requests raw mu-law/8kHz audio directly from Deepgram's TTS REST endpoint so it
// can be forwarded to Twilio's Media Stream with zero transcoding.
export async function synthesizeMulaw(text: string): Promise<Buffer> {
  const url =
    "https://api.deepgram.com/v1/speak?model=aura-2-thalia-en&encoding=mulaw&sample_rate=8000&container=none";

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
