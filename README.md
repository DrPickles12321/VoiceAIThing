# VoiceAIThing

A temporary chatbot for testing the six-question HOOS, JR. hip survey.

## Run the web app

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python web_app.py
```

Open **http://127.0.0.1:8000**. With no API key, the chatbot starts in offline
mode: choose None, Mild, Moderate, Severe, or Extreme, then confirm Yes or No.
For free-form answers, create `.env` using `.env.example`, set `OPENAI_API_KEY`,
and restart the server. Select OpenAI in the mode dropdown. The key stays on
the server and OpenAI calls use your API credits.

The page includes chat bubbles, reply buttons, confirmation progress, a new
survey button, and a completed-answer summary. Changing mode starts a fresh
survey. Refreshing the page also starts over. This is text chat; audio is not
connected. Run a single server worker locally; sessions are in memory and
there is no user authentication or database. Do not expose this demo publicly.

## Test

```bash
python -m pytest -m 'not live'
```

See [INTELLIGENCE.md](INTELLIGENCE.md) for the engine, CLI, model setup and optional
live model evaluations. Live semantic tests require a key and incur API charges.
