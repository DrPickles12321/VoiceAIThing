# Contributing

This is a HackMIT hackathon project. Practically:

## Setup

- Node.js 20+ recommended.
- Each sub-project (`spike/`, and later `packages/server`, `packages/dashboard`) has its own
  `package.json` and its own `npm install` — there's no root install yet.
- Copy the relevant `.env.example` to `.env` in whichever package you're running and fill in
  real credentials (Twilio, Deepgram, Anthropic, Supabase). Never commit `.env` files or real
  API keys — `.gitignore` already excludes `.env`, keep it that way.

## Before pushing

- Run `npx tsc --noEmit` in whatever package you touched — keep the build green.
- If you touched call-flow/audio code, note in your PR description whether you actually placed
  a live test call and what you observed (see the environment note below) — don't just say
  "tested" if you only ran a typecheck.
- Update `docs/architecture.md` and/or `PRD.md` if your change materially changes the design or
  scope, so they stay a reliable source of truth rather than drifting from what's actually
  built.

## A note on testing live calls

Twilio and Deepgram require real outbound network access and a public HTTPS/WSS URL (e.g. via
ngrok) for their webhooks — this doesn't work from every environment (notably, not from
Claude Code's sandboxed remote execution environment; see `CLAUDE.md`). Test live calls from a
laptop or a host with real network access, using the run-book in `spike/README.md`.

## Branching

Work happens on feature branches off `main`; open a PR (draft is fine mid-build) rather than
pushing straight to `main`.
