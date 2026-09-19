from survey_intelligence import SurveyDefinition, SurveyEngine, SurveyQuestion
from survey_intelligence.models import SurveyState


def make_engine() -> SurveyEngine:
    return SurveyEngine(SurveyDefinition("test", (SurveyQuestion("stairs", "How are stairs?", ("none", "mild", "moderate", "severe", "extreme")),)))


def test_rambling_answer_requires_confirmation_before_save() -> None:
    engine = make_engine()
    engine.start()
    prompt = engine.receive_transcript("Stairs are terrible and I need to pull myself up using the railing.")
    assert engine.session.state == SurveyState.CONFIRMING
    assert "severe" in prompt
    assert engine.session.responses == {}
    engine.confirm("yes", "yes")
    assert engine.session.state == SurveyState.COMPLETE
    assert engine.session.responses["stairs"].value == "severe"


def test_no_cannot_save_candidate() -> None:
    engine = make_engine()
    engine.start()
    engine.receive_transcript("severe")
    engine.confirm("no", "no")
    assert engine.session.state == SurveyState.LISTENING
    assert engine.session.responses == {}


def test_safety_language_escalates_without_extraction() -> None:
    engine = make_engine()
    engine.start()
    message = engine.receive_transcript("My leg has sudden swelling and I can barely move.")
    assert engine.session.state == SurveyState.ESCALATED
    assert engine.session.responses == {}
    assert "care team" in message
