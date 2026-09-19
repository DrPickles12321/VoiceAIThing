"""Local chatbot demo: python web_app.py. Sessions last until server restart."""
import os
from pathlib import Path
from threading import RLock
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from survey_intelligence.extractor import keyword_extractor
from survey_intelligence.service import SurveyService
from survey_intelligence.surveys import HOOS_JR

ROOT = Path(__file__).resolve().parent


class NewSession(BaseModel):
    mode: Literal["offline", "openai"] = "offline"


class Turn(BaseModel):
    transcript: str = Field(min_length=1, max_length=8000)


def create_app():
    load_dotenv(ROOT / ".env")
    app = FastAPI(title="VoiceAIThing local survey demo")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    sessions = {}
    lock = RLock()

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        # No cross-origin access to the local model-backed endpoints.
        origin = request.headers.get("origin")
        if request.method == "POST" and origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Use the app from its local address."}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'"
        return response

    @app.get("/api/config")
    def config():
        ready = bool(os.getenv("OPENAI_API_KEY"))
        return {"openai_available": ready,
                "default_mode": "openai" if ready and os.getenv("SURVEY_EXTRACTOR", "openai") == "openai" else "offline"}

    @app.post("/api/sessions")
    def new_session(body: NewSession):
        extractor = keyword_extractor
        if body.mode == "openai":
            if not os.getenv("OPENAI_API_KEY"):
                raise HTTPException(503, "Add OPENAI_API_KEY to .env and restart the server to enable AI mode.")
            from survey_intelligence.openai_extractor import OpenAIExtractor
            extractor = OpenAIExtractor()
        service = SurveyService(HOOS_JR, extractor)
        result = service.create_session()
        with lock:
            sessions[result["session_id"]] = service
        return {**result, "mode": body.mode}

    @app.post("/api/sessions/{session_id}/turns")
    def handle_turn(session_id: str, body: Turn):
        if not body.transcript.strip():
            raise HTTPException(422, "Enter an answer first.")
        with lock:
            service = sessions.get(session_id)
        if service is None:
            raise HTTPException(404, "Session expired. Start a new survey.")
        try:
            return service.handle_turn(session_id, body.transcript)
        except RuntimeError as exc:
            raise HTTPException(409, "This survey has ended. Start a new survey.") from exc

    @app.get("/")
    def index():
        return FileResponse(ROOT / "web" / "index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
