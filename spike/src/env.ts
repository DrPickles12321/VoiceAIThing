import "dotenv/config";
import { z } from "zod";

const envSchema = z.object({
  DEEPGRAM_API_KEY: z.string().min(1),
  ANTHROPIC_API_KEY: z.string().min(1),
  ANTHROPIC_MODEL: z.string().default("claude-sonnet-5"),
  PORT: z.coerce.number().default(3000),

  // Gait-checker handoff (see docs/architecture.md's integration contract).
  GAIT_CHECKER_BASE_URL: z.string().url().default("https://gaitguard.ai"),
  PATIENT_CODE: z.string().default("RGN-0417"),
  PATIENT_PHONE_NUMBER: z.string().optional(), // E.164; required only for a real SMS send

  // Optional: sending a real SMS needs Twilio's Messaging API. Leave unset to fall back to
  // just speaking/logging the link (see docs/architecture.md's "New SMS dependency" risk).
  TWILIO_ACCOUNT_SID: z.string().optional(),
  TWILIO_AUTH_TOKEN: z.string().optional(),
  TWILIO_SMS_FROM_NUMBER: z.string().optional(),
});

export const env = envSchema.parse(process.env);
