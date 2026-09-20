from __future__ import annotations

import asyncio
import base64
import json

import pytest
from fastapi.testclient import TestClient

import phone_app
from app.telephony.config import load_settings
from app.telephony.deepgram_stt import SpeechEvent

ENV = {
    "DEEPGRAM_API_KEY": "dg-key",
    "TWILIO_ACCOUNT_SID": "AC123",
    "TWILIO_AUTH_TOKEN": "token",
    "TWILIO_FROM_NUMBER": "+15005550006",
    "PUBLIC_BASE_URL": "https://tunnel.example.com",
}


class ScriptedTranscriber:
    """Stand-in for Deepgram that replays a fixed event script."""

    script: list[SpeechEvent] = []

    def __init__(self, **kwargs):
        self.audio_frames: list[bytes] = []

    async def __aenter__(self):
        return self

    async def close(self) -> None:
        return None

    async def send_audio(self, frame: bytes) -> None:
        self.audio_frames.append(frame)

    async def events(self):
        for event in self.script:
            await asyncio.sleep(0)
            yield event
        while True:
            await asyncio.sleep(0.05)


@pytest.fixture
def client(monkeypatch):
    async def fake_tts(text: str, api_key: str, model: str) -> bytes:
        return b"\xff" * 320

    monkeypatch.setattr(phone_app, "synthesize_mulaw_async", fake_tts)
    monkeypatch.setattr(phone_app, "DeepgramTranscriber", ScriptedTranscriber)
    monkeypatch.setattr(phone_app, "_signature_ok", lambda *args, **kwargs: True)
    return TestClient(phone_app.create_app(load_settings(ENV)))


def test_config_reports_ready(client):
    body = client.get("/api/config").json()
    assert body == {
        "deepgram_configured": True,
        "twilio_configured": True,
        "public_base_url": "https://tunnel.example.com",
        "ready": True,
    }


def test_voice_webhook_returns_stream_twiml(client):
    response = client.post(
        "/twilio/voice?patient_code=RGN-0417&session_id=sess-1", data={"CallSid": "CA1"}
    )
    assert response.status_code == 200
    assert 'url="wss://tunnel.example.com/twilio/media"' in response.text
    assert 'value="RGN-0417"' in response.text


def test_voice_webhook_hangs_up_on_unknown_patient(client):
    response = client.post("/twilio/voice?patient_code=NOPE", data={"CallSid": "CA1"})
    assert "<Hangup/>" in response.text
    assert "Stream" not in response.text


def test_start_call_records_dialing_before_twilio_connects(client, monkeypatch):
    async def fake_place_call(**kwargs):
        return phone_app.twilio.PlacedCall(
            call_sid="CA1", status="queued", to_number=kwargs["to_number"]
        )

    monkeypatch.setattr(phone_app.twilio, "place_call_async", fake_place_call)
    response = client.post(
        "/api/calls", json={"to_number": "+14155550123", "patient_code": "RGN-0417"}
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]

    record = client.get(f"/api/calls/{session_id}").json()
    assert record["status"] == "dialing"
    assert record["patient_code"] == "RGN-0417"


def test_status_webhook_marks_a_call_the_patient_never_answered(client, monkeypatch):
    async def fake_place_call(**kwargs):
        return phone_app.twilio.PlacedCall(
            call_sid="CA2", status="queued", to_number=kwargs["to_number"]
        )

    monkeypatch.setattr(phone_app.twilio, "place_call_async", fake_place_call)
    session_id = client.post(
        "/api/calls", json={"to_number": "+14155550123", "patient_code": "RGN-0417"}
    ).json()["session_id"]

    client.post("/twilio/status", data={"CallSid": "CA2", "CallStatus": "no-answer"})

    record = client.get(f"/api/calls/{session_id}").json()
    assert record["status"] == "completed"
    assert record["final_status"] == "no-answer"
    assert record["call_sid"] == "CA2"


def test_start_call_rejects_unknown_patient(client):
    response = client.post("/api/calls", json={"to_number": "+14155550123", "patient_code": "NOPE"})
    assert response.status_code == 404


def test_start_call_rejects_non_e164_number(client):
    response = client.post("/api/calls", json={"to_number": "4155550123"})
    assert response.status_code == 400


def test_media_stream_answers_and_records_the_survey(client):
    ScriptedTranscriber.script = [
        SpeechEvent("transcript", "moderate", True),
        SpeechEvent("utterance_end"),
        SpeechEvent("transcript", "yes", True),
        SpeechEvent("utterance_end"),
    ]
    with client.websocket_connect("/twilio/media") as websocket:
        websocket.send_text(
            json.dumps(
                {
                    "event": "start",
                    "streamSid": "MZ1",
                    "start": {
                        "streamSid": "MZ1",
                        "callSid": "CA1",
                        "customParameters": {"patientCode": "RGN-0417", "sessionId": "sess-1"},
                    },
                }
            )
        )
        websocket.send_text(
            json.dumps(
                {
                    "event": "media",
                    "media": {"track": "inbound", "payload": base64.b64encode(b"\x7f" * 160).decode()},
                }
            )
        )
        outbound = []
        while not outbound or outbound[-1]["event"] != "mark":
            outbound.append(json.loads(websocket.receive_text()))
        websocket.send_text(json.dumps({"event": "stop"}))

    assert outbound[0]["event"] == "media"
    assert outbound[0]["streamSid"] == "MZ1"
    assert base64.b64decode(outbound[0]["media"]["payload"]) == b"\xff" * 160
    assert outbound[-1] == {"event": "mark", "streamSid": "MZ1", "mark": {"name": "prompt-1"}}

    record = client.app.state.persistence.calls["sess-1"]
    assert record.answers == [{"question_id": "hoos_stairs", "value": "moderate"}]
    assert any(line.startswith("patient: moderate") for line in record.transcript)
