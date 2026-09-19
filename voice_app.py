"""Local desktop voice survey app.

Run with ``python voice_app.py`` and open http://127.0.0.1:8000.
The browser owns microphone capture and speech playback. Deepgram transcription
is performed by the local server so the API key never reaches the browser.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4
from urllib import request

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.patient_repository import InMemoryPatientRepository
from app.survey_engine import SafeSurveyEngine

ROOT = Path(__file__).resolve().parent
MAX_AUDIO_BYTES = 10 * 1024 * 1024


def transcribe_with_deepgram(audio: bytes, content_type: str) -> str:
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPGRAM_API_KEY is not configured.")
    if not audio:
        raise ValueError("The recorded audio was empty.")

    media_type = content_type or "audio/webm"
    endpoint = (
        "https://api.deepgram.com/v1/listen"
        "?model=nova-3&smart_format=true&punctuate=true&language=en-US"
    )
    req = request.Request(
        endpoint,
        data=audio,
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": media_type,
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            payload = json.load(response)
    except Exception as exc:
        raise RuntimeError("Deepgram transcription failed.") from exc

    try:
        transcript = payload["results"]["channels"][0]["alternatives"][0]["transcript"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Deepgram returned no usable transcript.") from exc
    transcript = transcript.strip()
    if not transcript:
        raise RuntimeError("Deepgram returned an empty transcript.")
    return transcript


def create_app() -> FastAPI:
    load_dotenv(ROOT / ".env")
    app = FastAPI(title="VoiceAIThing desktop voice survey")
    sessions: dict[str, SafeSurveyEngine] = {}
    lock = RLock()

    @app.get("/api/config")
    def config() -> dict[str, bool]:
        return {"deepgram_configured": bool(os.getenv("DEEPGRAM_API_KEY"))}

    @app.post("/api/sessions")
    def create_session(patient_code: str = "RGN-0417") -> dict[str, object]:
        try:
            engine = SafeSurveyEngine(InMemoryPatientRepository(), patient_code)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session_id = str(uuid4())
        with lock:
            sessions[session_id] = engine
        return {
            "session_id": session_id,
            "prompt": engine.start(),
            **engine.snapshot(),
        }

    @app.post("/api/sessions/{session_id}/audio")
    async def handle_audio(session_id: str, audio: UploadFile = File(...)) -> dict[str, object]:
        with lock:
            engine = sessions.get(session_id)
        if engine is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        if not os.getenv("DEEPGRAM_API_KEY"):
            raise HTTPException(status_code=503, detail="Set DEEPGRAM_API_KEY in .env first.")

        content = await audio.read(MAX_AUDIO_BYTES + 1)
        if len(content) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio recording is too large.")
        try:
            transcript = transcribe_with_deepgram(content, audio.content_type or "audio/webm")
            prompt, answer = engine.handle_response(transcript)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "transcript": transcript,
            "prompt": prompt,
            "answer": answer.normalized_value if answer else None,
            **engine.snapshot(),
        }

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(ROOT / "voice_web" / "index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "voice_web"), name="static")
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
