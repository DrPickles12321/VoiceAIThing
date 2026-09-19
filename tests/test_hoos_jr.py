from survey_intelligence.engine import SurveyEngine
from survey_intelligence.extractor import keyword_extractor
from survey_intelligence.service import SurveyService
from survey_intelligence.surveys import HOOS_JR


def test_items_match_image_and_preserve_timeframe():
    assert [q.id for q in HOOS_JR.questions] == [
        "pain_stairs", "pain_uneven_surface", "function_rising",
        "function_bending", "function_bed", "function_sitting",
    ]
    for index, question in enumerate(HOOS_JR.questions):
        assert question.options == ("none", "mild", "moderate", "severe", "extreme")
        assert "last week" in question.prompt
        assert ("hip pain" in question.prompt) if index < 2 else ("difficulty" in question.prompt)
    assert "uneven surface" in HOOS_JR.questions[1].prompt
    assert "maintaining hip position" in HOOS_JR.questions[4].prompt


def test_full_six_question_survey_requires_six_confirmations():
    service = SurveyService(HOOS_JR, keyword_extractor)
    turn = service.create_session()
    assert "HOOS, JR. HIP SURVEY" in turn["prompt"]
    sid = turn["session_id"]
    for index, (question, answer) in enumerate(zip(HOOS_JR.questions, ["none", "mild", "moderate", "severe", "extreme", "mild"])):
        assert turn["current_question"] == question.id
        candidate = service.handle_turn(sid, answer)
        assert candidate["state"] == "confirming"
        assert candidate["answered_count"] == index
        turn = service.handle_turn(sid, "yes")
        assert turn["answered_count"] == index + 1
        assert turn["responses"][question.id]["raw_response"] == answer
        assert turn["responses"][question.id]["confirmation_transcript"] == "yes"
    assert turn["state"] == "complete"
    assert turn["question_count"] == 6
    assert turn["survey_id"] == "hoos-jr"


def test_hip_pain_does_not_use_old_stairs_difficulty_heuristic():
    engine = SurveyEngine(HOOS_JR)
    engine.start()
    engine.handle_turn("I pull myself up using the railing")
    assert engine.snapshot()["state"] == "clarifying"
