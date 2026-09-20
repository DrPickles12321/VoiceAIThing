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
import re
from collections.abc import Awaitable
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
FRAME_SECONDS = 0.02
PLAYBACK_LEAD_SECONDS = 2.0
SPEECH_CHUNK_CHARS = 90
CARRIER_FAILURES = {"busy", "no-answer", "failed", "canceled"}

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
        self._closed = False
        self._inbound_frames = 0
        self._turn_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task[None]] = []
        self._playback_task: asyncio.Task[None] | None = None

    async def run(self) -> None:
        await self.websocket.accept()
        try:
            while not self._closed:
                message = json.loads(await self.websocket.receive_text())
                event = message.get("event")
                if event == "start":
                    await self._on_start(message)
                elif event == "media":
                    await self._on_media(message)
                elif event == "mark":
                    await self._on_mark(message)
                elif event == "stop":
                    logger.info("Stream %s stopped by Twilio", self.stream_sid)
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("Media stream failed")
        finally:
            self._cancel_silence_timer()
            for task in self._tasks:
                task.cancel()
            if self.transcriber is not None:
                await self.transcriber.close()
            await self._close()

    async def _on_start(self, message: dict[str, Any]) -> None:
        start = message.get("start", {})
        self.stream_sid = start.get("streamSid") or message.get("streamSid")
        parameters = start.get("customParameters", {}) or {}
        patient_code = parameters.get("patientCode", "")
        session_id = parameters.get("sessionId") or start.get("callSid") or str(uuid4())
        logger.info(
            "Stream %s started for call %s (patient %s, format %s)",
            self.stream_sid,
            start.get("callSid"),
            patient_code,
            start.get("mediaFormat"),
        )
        try:
            engine = SafeSurveyEngine(self.repository, patient_code)
        except PatientNotFoundError:
            logger.error("Unknown patient code on call %s", session_id)
            await self._close()
            return

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
        # Both the survey turns and the speech events run off the receive loop so
        # inbound audio keeps flowing to Deepgram while a prompt is playing.
        self._tasks.append(asyncio.create_task(self._pump_speech_events()))
        self._tasks.append(asyncio.create_task(self._run_turn(self.session.begin())))

    async def _on_media(self, message: dict[str, Any]) -> None:
        if self.transcriber is None:
            return
        media = message.get("media", {})
        if media.get("track") not in (None, "inbound"):
            return
        payload = media.get("payload")
        if payload:
            self._inbound_frames += 1
            if self._inbound_frames % 250 == 0:
                logger.info(
                    "Stream %s received %d inbound frames", self.stream_sid, self._inbound_frames
                )
            await self.transcriber.send_audio(base64.b64decode(payload))

    async def _on_mark(self, message: dict[str, Any]) -> None:
        name = message.get("mark", {}).get("name")
        logger.info("Stream %s finished playing %s", self.stream_sid, name)
        if name == self.hangup_mark:
            await self._close()
            return
        self.bot_speaking = False
        self._start_silence_timer()

    async def _run_turn(self, coroutine: Awaitable[bool | None]) -> None:
        """Serialize survey turns; one prompt finishes speaking before the next."""

        try:
            async with self._turn_lock:
                finished = await coroutine
            if finished:
                await self._end_after_playback()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Survey turn failed")

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
                await self._run_turn(self.session.flush_utterance())

    async def _speak(self, text: str) -> None:
        if not self.settings.deepgram_api_key or self.stream_sid is None:
            logger.warning("Cannot speak: deepgram key or stream missing")
            return
        self._cancel_silence_timer()
        self.bot_speaking = True
        self._mark_counter += 1
        self._last_mark = f"prompt-{self._mark_counter}"
        playback = asyncio.create_task(self._stream_speech(text, self._last_mark))
        self._playback_task = playback
        # Waiting this way keeps a barge-in cancellation local to the playback.
        await asyncio.wait({playback})

    async def _stream_speech(self, text: str, mark: str) -> None:
        """Synthesize the prompt piece by piece and play it at speaking speed.

        A whole prompt takes seconds to synthesize, which the caller would hear
        as dead air, so each sentence group is rendered while the previous one
        plays. Frames go out just ahead of playback: Twilio buffers everything
        it receives, so a burst would both make barge-in meaningless and starve
        the inbound audio Deepgram expects.
        """

        loop = asyncio.get_running_loop()
        started = loop.time()
        sent_frames = 0
        chunks = speech_chunks(text)
        pending = asyncio.create_task(self._synthesize(chunks[0]))
        for index, chunk in enumerate(chunks):
            audio = await pending
            if index + 1 < len(chunks):
                pending = asyncio.create_task(self._synthesize(chunks[index + 1]))
            logger.info(
                "Speaking %d chars as %.1fs of audio on stream %s",
                len(chunk),
                len(audio) / 8000,
                self.stream_sid,
            )
            for frame in frames(audio):
                await self._send(
                    {
                        "event": "media",
                        "streamSid": self.stream_sid,
                        "media": {"payload": base64.b64encode(frame).decode("ascii")},
                    }
                )
                sent_frames += 1
                ahead = (
                    started
                    + sent_frames * FRAME_SECONDS
                    + PLAYBACK_LEAD_SECONDS
                    - loop.time()
                )
                if ahead > 0:
                    await asyncio.sleep(ahead)
        await self._send({"event": "mark", "streamSid": self.stream_sid, "mark": {"name": mark}})

    async def _synthesize(self, text: str) -> bytes:
        return await synthesize_mulaw_async(
            text, self.settings.deepgram_api_key, self.settings.tts_model
        )

    async def _clear_playback(self) -> None:
        self.bot_speaking = False
        task, self._playback_task = self._playback_task, None
        if task is not None:
            task.cancel()
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
        await self._run_turn(self.session.handle_silence())

    async def _send(self, message: dict[str, Any]) -> None:
        async with self._send_lock:
            await self.websocket.send_text(json.dumps(message))

    async def _close(self) -> None:
        self._closed = True
        try:
            await self.websocket.close()
        except (RuntimeError, WebSocketDisconnect):
            pass


def speech_chunks(text: str, limit: int = SPEECH_CHUNK_CHARS) -> list[str]:
    """Group a prompt into sentence-sized pieces so speech can start quickly."""

    chunks: list[str] = []
    current = ""
    for sentence in re.findall(r"[^.!?]+[.!?]*\s*", text.strip()) or [text.strip()]:
        if current and len(current) + len(sentence) > limit:
            chunks.append(current.strip())
            current = sentence
        else:
            current += sentence
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text]


def create_app(settings: TelephonySettings | None = None) -> FastAPI:
    load_dotenv(ROOT / ".env")
    resolved = settings or load_settings()
    app = FastAPI(title="VoiceAIThing phone survey")
    repository = InMemoryPatientRepository()
    persistence = InMemoryPersistence()
    sessions_by_call_sid: dict[str, str] = {}
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
        record.call_sid = call.call_sid
        record.to_number = call.to_number
        record.carrier_status = call.status
        sessions_by_call_sid[call.call_sid] = session_id
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
            "call_sid": record.call_sid,
            "to_number": record.to_number,
            "carrier_status": record.carrier_status,
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
        record = persistence.calls.get(sessions_by_call_sid.get(CallSid, ""))
        if record is not None and CallStatus:
            record.carrier_status = CallStatus
            if CallStatus == "in-progress":
                record.status = "in_progress"
            elif CallStatus in CARRIER_FAILURES and record.final_status is None:
                record.status = "completed"
                record.final_status = CallStatus
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

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s %(message)s")

    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
