import twilio from "twilio";
import { env } from "./env.js";

// Sends the gait-checker link via Twilio's Messaging API -- a much lighter integration than
// the Voice/Media Streams product this project dropped in the browser-mic pivot (one HTTP
// call, no telephony audio handling). Falls back to logging the link if SMS isn't configured
// (missing credentials or destination number), per docs/architecture.md's fallback note --
// this is an acceptable hackathon-demo degradation, not an error.
export async function sendLinkSms(link: string): Promise<{ sent: boolean }> {
  const { TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_SMS_FROM_NUMBER, PATIENT_PHONE_NUMBER } =
    env;

  if (!TWILIO_ACCOUNT_SID || !TWILIO_AUTH_TOKEN || !TWILIO_SMS_FROM_NUMBER || !PATIENT_PHONE_NUMBER) {
    console.log(`[sms] not configured -- falling back to logging the link: ${link}`);
    return { sent: false };
  }

  try {
    const client = twilio(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN);
    await client.messages.create({
      to: PATIENT_PHONE_NUMBER,
      from: TWILIO_SMS_FROM_NUMBER,
      body: `Here's your gait check-in link: ${link}`,
    });
    console.log(`[sms] sent link to ${PATIENT_PHONE_NUMBER}`);
    return { sent: true };
  } catch (err) {
    console.error("[sms] send failed, falling back to logging the link", err);
    console.log(`[sms] link: ${link}`);
    return { sent: false };
  }
}
