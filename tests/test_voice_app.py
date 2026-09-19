from app.patient_repository import InMemoryPatientRepository
from app.survey_engine import SafeSurveyEngine
from voice_app import create_app, transcribe_with_deepgram


def test_voice_app_exposes_desktop_routes(monkeypatch):
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/" in paths
    assert "/api/sessions" in paths
    assert "/api/sessions/{session_id}/audio" in paths


def test_voice_flow_uses_existing_guarded_engine():
    engine = SafeSurveyEngine(InMemoryPatientRepository(), "RGN-0417")
    prompt = engine.start()
    assert "Question 1 of 6" in prompt
