import "dotenv/config";
import { z } from "zod";

const envSchema = z.object({
  DEEPGRAM_API_KEY: z.string().min(1),
  ANTHROPIC_API_KEY: z.string().min(1),
  ANTHROPIC_MODEL: z.string().default("claude-sonnet-5"),
  PORT: z.coerce.number().default(3000),
});

export const env = envSchema.parse(process.env);
