"""Phone survey server: Twilio carries the call, Deepgram does the speech.

Run with ``python phone_app.py`` behind a public HTTPS tunnel and set
``PUBLIC_BASE_URL`` to that tunnel. ``POST /api/calls`` dials the patient,
Twilio fetches TwiML from ``/twilio/voice`` and opens a bidirectional media
stream to ``/twilio/media``, where the survey runs turn by turn.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.patient_repository import InMemoryPatientRepository, PatientNotFoundError
from app.persistence import InMemoryPersistence
from app.survey_engine import SafeSurveyEngine
from app.telephony import twilio
from app.telephony.call_session import PhoneCallSession
from app.telephony.config import TelephonyConfigurationError, TelephonySettings, load_settings
from app.telephony.deepgram_stt import DeepgramTranscriber
from app.telephony.deepgram_tts import frames, synthesize_mulaw_async

ROOT = Path(__file__).resolve().parent
VOICE_PATH = "/twilio/voice"
STATUS_PATH = "/twilio/status"
MEDIA_PATH = "/twilio/media"
SILENCE_TIMEOUT_SECONDS = 8.0

logger = logging.getLogger("phone_app")


class CallRequest(BaseModel):
    to_number: str
    patient_code: str = "RGN-0417"


class MediaStreamBridge:
    """Glue between one Twilio media stream and one Deepgram transcription."""

    def __init__(
        self,
        websocket: WebSocket,
        settings: TelephonySettings,
        repository: InMemoryPatientRepository,
        persistence: InMemoryPersistence,
        transcriber_factory=None,
    ):
        self.websocket = websocket
        self.settings = settings
        self.repository = repository
        self.persistence = persistence
        self.transcriber_factory = transcriber_factory or DeepgramTranscriber
        self.stream_sid: str | None = None
        self.session: PhoneCallSession | None = None
        self.transcriber: DeepgramTranscriber | None = None
        self.bot_speaking = False
        self.hangup_mark: str | None = None
        self._send_lock = asyncio.Lock()
        self._silence_task: asyncio.Task[None] | None = None
        self._mark_counter = 0
        self._last_mark: str | None = None

    async def run(self) -> None:
        await self.websocket.accept()
        events_task: asyncio.Task[None] | None = None
        try:
            while True:
                message = json.loads(await self.websocket.receive_text())
                event = message.get("event")
                if event == "start":
                    events_task = await self._on_start(message)
                elif event == "media":
                    await self._on_media(message)
                elif event == "mark":
                    await self._on_mark(message)
                elif event == "stop":
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("Media stream failed")
        finally:
            self._cancel_silence_timer()
            if events_task is not None:
                events_task.cancel()
            if self.transcriber is not None:
                await self.transcriber.close()
            await self._close()

    async def _on_start(self, message: dict[str, Any]) -> asyncio.Task[None] | None:
        start = message.get("start", {})
        self.stream_sid = start.get("streamSid") or message.get("streamSid")
        parameters = start.get("customParameters", {}) or {}
        patient_code = parameters.get("patientCode", "")
        session_id = parameters.get("sessionId") or start.get("callSid") or str(uuid4())
        try:
            engine = SafeSurveyEngine(self.repository, patient_code)
        except PatientNotFoundError:
            logger.error("Unknown patient code on call %s", session_id)
            await self._close()
            return None

        self.session = PhoneCallSession(
            engine,
            speak=self._speak,
            session_id=session_id,
            persistence=self.persistence,
        )
        self.transcriber = self.transcriber_factory(
            api_key=self.settings.deepgram_api_key or "",
            model=self.settings.stt_model,
            utterance_end_ms=self.settings.utterance_end_ms,
        )
        await self.transcriber.__aenter__()
        task = asyncio.create_task(self._pump_speech_events())
        await self.session.begin()
        return task

    async def _on_media(self, message: dict[str, Any]) -> None:
        if self.transcriber is None:
            return
        media = message.get("media", {})
        if media.get("track") not in (None, "inbound"):
            return
        payload = media.get("payload")
        if payload:
            await self.transcriber.send_audio(base64.b64decode(payload))

    async def _on_mark(self, message: dict[str, Any]) -> None:
        name = message.get("mark", {}).get("name")
        if name == self.hangup_mark:
            await self._close()
            return
        self.bot_speaking = False
        self._start_silence_timer()

    async def _pump_speech_events(self) -> None:
        assert self.transcriber is not None
        async for event in self.transcriber.events():
            if self.session is None:
                continue
            if event.kind == "speech_started":
                self._cancel_silence_timer()
                if self.bot_speaking:
                    await self._clear_playback()
            elif event.kind == "transcript" and event.is_final:
                self._cancel_silence_timer()
                self.session.add_transcript(event.text)
            elif event.kind == "utterance_end":
                finished = await self.session.flush_utterance()
                if finished:
                    await self._end_after_playback()

    async def _speak(self, text: str) -> None:
        if not self.settings.deepgram_api_key or self.stream_sid is None:
            return
        audio = await synthesize_mulaw_async(
            text, self.settings.deepgram_api_key, self.settings.tts_model
        )
        self._cancel_silence_timer()
        self.bot_speaking = True
        for frame in frames(audio):
            await self._send(
                {
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": base64.b64encode(frame).decode("ascii")},
                }
            )
        self._mark_counter += 1
        self._last_mark = f"prompt-{self._mark_counter}"
        await self._send(
            {"event": "mark", "streamSid": self.stream_sid, "mark": {"name": self._last_mark}}
        )

    async def _clear_playback(self) -> None:
        self.bot_speaking = False
        await self._send({"event": "clear", "streamSid": self.stream_sid})

    async def _end_after_playback(self) -> None:
        self.hangup_mark = self._last_mark
        if not self.bot_speaking:
            await self._close()

    def _start_silence_timer(self) -> None:
        self._cancel_silence_timer()
        if self.session is None or self.session.finished:
            return
        self._silence_task = asyncio.create_task(self._silence_watchdog())

    def _cancel_silence_timer(self) -> None:
        task, self._silence_task = self._silence_task, None
        if task is not None:
            task.cancel()

    async def _silence_watchdog(self) -> None:
        try:
            await asyncio.sleep(SILENCE_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            return
        if self.session is None:
            return
        if await self.session.handle_silence():
            await self._end_after_playback()

    async def _send(self, message: dict[str, Any]) -> None:
        async with self._send_lock:
            await self.websocket.send_text(json.dumps(message))

    async def _close(self) -> None:
        try:
            await self.websocket.close()
        except RuntimeError:
            pass


def create_app(settings: TelephonySettings | None = None) -> FastAPI:
    load_dotenv(ROOT / ".env")
    resolved = settings or load_settings()
    app = FastAPI(title="VoiceAIThing phone survey")
    repository = InMemoryPatientRepository()
    persistence = InMemoryPersistence()
    app.state.settings = resolved
    app.state.persistence = persistence

    @app.get("/api/config")
    def config() -> dict[str, object]:
        return {
            "deepgram_configured": resolved.deepgram_ready,
            "twilio_configured": resolved.twilio_ready,
            "public_base_url": resolved.public_base_url,
            "ready": resolved.ready,
        }

    @app.post("/api/calls")
    async def start_call(payload: CallRequest) -> dict[str, object]:
        try:
            resolved.require_outbound()
        except TelephonyConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        try:
            patient = repository.lookup_patient(payload.patient_code)
        except PatientNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        session_id = str(uuid4())
        answer_url = (
            f"{resolved.webhook_url(VOICE_PATH)}"
            f"?patient_code={payload.patient_code}&session_id={session_id}"
        )
        try:
            call = await twilio.place_call_async(
                account_sid=resolved.twilio_account_sid,
                auth_token=resolved.twilio_auth_token,
                to_number=payload.to_number,
                from_number=resolved.twilio_from_number,
                answer_url=answer_url,
                status_callback_url=resolved.webhook_url(STATUS_PATH),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except twilio.TwilioError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        record = persistence.start_call(
            session_id, payload.patient_code, patient.condition_category.value
        )
        record.status = "dialing"
        return {
            "call_sid": call.call_sid,
            "status": call.status,
            "to_number": call.to_number,
            "session_id": session_id,
        }

    @app.get("/api/calls/{session_id}")
    def call_record(session_id: str) -> dict[str, object]:
        record = persistence.calls.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="No call record for that session.")
        return {
            "session_id": record.session_id,
            "patient_code": record.patient_code,
            "condition_category": record.condition_category,
            "status": record.status,
            "final_status": record.final_status,
            "transcript": record.transcript,
            "answers": record.answers,
        }

    @app.post(VOICE_PATH)
    async def voice(request: Request) -> Response:
        form = dict(await request.form())
        if not _signature_ok(resolved, request, form):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature.")
        patient_code = request.query_params.get("patient_code", "")
        session_id = request.query_params.get("session_id") or form.get("CallSid", str(uuid4()))
        try:
            repository.lookup_patient(patient_code)
        except PatientNotFoundError:
            return Response(
                content=twilio.hangup_twiml(
                    "We could not find your record, so this call will end now."
                ),
                media_type="application/xml",
            )
        return Response(
            content=twilio.media_stream_twiml(
                resolved.websocket_url(MEDIA_PATH),
                {"patientCode": patient_code, "sessionId": str(session_id)},
            ),
            media_type="application/xml",
        )

    @app.post(STATUS_PATH)
    async def status(request: Request, CallSid: str = Form(""), CallStatus: str = Form("")) -> Response:
        logger.info("Call %s status %s", CallSid, CallStatus)
        return Response(status_code=204)

    @app.websocket(MEDIA_PATH)
    async def media(websocket: WebSocket) -> None:
        await MediaStreamBridge(websocket, resolved, repository, persistence).run()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(ROOT / "phone_web" / "index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "phone_web"), name="static")
    return app


def _signature_ok(settings: TelephonySettings, request: Request, form: dict[str, Any]) -> bool:
    if not settings.twilio_auth_token or not settings.public_base_url:
        return True
    signature = request.headers.get("X-Twilio-Signature", "")
    url = f"{settings.public_base_url.rstrip('/')}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    return twilio.validate_signature(
        settings.twilio_auth_token, url, {k: str(v) for k, v in form.items()}, signature
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
