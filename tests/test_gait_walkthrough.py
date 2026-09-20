from unittest.mock import Mock

from app.call_flow import CheckUpCall
from app.conversation_policy import MEDICAL_BOUNDARY
from app.gait_walkthrough import (
    CONGRATULATIONS,
    MAX_HELP_ATTEMPTS,
    REVIEW,
    STOPPED,
    TRANSITION,
    WAITING,
    WALKTHROUGH_STEPS,
    GaitWalkthroughGuide,
    OpenAIWalkthroughInterpreter,
    StepInterpretation,
    build_walkthrough_interpreter,
    validated_step_interpretation,
)
from app.patient_repository import InMemoryPatientRepository
from app import conversation_policy as speech


def finished_survey(**kwargs) -> CheckUpCall:
    call = CheckUpCall(InMemoryPatientRepository(), "RGN-0417", **kwargs)
    call.start()
    for _ in range(5):
        call.handle_response("mild")
    return call


class FixedInterpreter:
    def __init__(self, *results):
        self.results = iter(results)
        self.seen = []

    def interpret(self, transcript, step):
        self.seen.append((transcript, step.id))
        return next(self.results)


def test_guide_speaks_every_step_verbatim_and_congratulates_at_the_end():
    guide = GaitWalkthroughGuide()
    opening = guide.start()
    assert opening == f"{TRANSITION} {WALKTHROUGH_STEPS[0].instruction}"
    assert guide.snapshot()["state"] == "guiding"
    for step in WALKTHROUGH_STEPS[1:]:
        prompt = guide.handle_response("ready")
        assert prompt.endswith(step.instruction)
        assert guide.snapshot()["current_step"] == step.id
    assert guide.handle_response("all done") == CONGRATULATIONS
    assert guide.snapshot()["state"] == "complete"
    assert guide.is_active is False
    # Terminal states stay put, whatever is heard afterwards.
    assert guide.handle_response("ready") == CONGRATULATIONS


def test_not_ready_waits_without_moving_on_and_repeat_reads_the_same_step():
    guide = GaitWalkthroughGuide()
    guide.start()
    assert guide.handle_response("hold on") == WAITING
    assert guide.snapshot() == {
        "state": "paused", "step_index": 0, "step_count": len(WALKTHROUGH_STEPS),
        "current_step": "open_link", "help_attempts": 0, "needs_human_review": False,
    }
    assert guide.handle_response("the weather is nice today") == WAITING  # Unclear while paused keeps waiting.
    assert guide.snapshot()["help_attempts"] == 0
    assert guide.handle_response("repeat that") == f"Of course. {WALKTHROUGH_STEPS[0].instruction}"
    assert guide.snapshot()["state"] == "guiding"
    assert guide.snapshot()["step_index"] == 0


def test_trouble_and_unclear_replies_retry_the_step_then_escalate():
    guide = GaitWalkthroughGuide()
    guide.start()
    first = guide.handle_response("I don't see it")
    assert first.endswith(WALKTHROUGH_STEPS[0].instruction)
    assert guide.snapshot()["help_attempts"] == 1
    second = guide.handle_response("the cat is on the roof")
    assert second.endswith(WALKTHROUGH_STEPS[0].instruction)
    assert guide.snapshot()["help_attempts"] == 2
    assert guide.handle_response("it's not working") == REVIEW
    assert guide.snapshot()["help_attempts"] == MAX_HELP_ATTEMPTS
    assert guide.snapshot()["state"] == "escalated"
    assert guide.snapshot()["needs_human_review"] is True


def test_progress_resets_the_help_counter_for_the_next_step():
    guide = GaitWalkthroughGuide()
    guide.start()
    guide.handle_response("help")
    guide.handle_response("help")
    guide.handle_response("it's open")
    assert guide.snapshot()["help_attempts"] == 0
    assert guide.snapshot()["current_step"] == "find_space"


def test_stop_ends_the_walkthrough_and_medical_questions_get_the_boundary_only():
    guide = GaitWalkthroughGuide(interpreter=FixedInterpreter(
        StepInterpretation("medical_question", "You're doing well."),
    ))
    guide.start()
    prompt = guide.handle_response("should I take my pain pills first?")
    assert prompt == f"{MEDICAL_BOUNDARY} {WALKTHROUGH_STEPS[0].instruction}"
    assert guide.snapshot()["step_index"] == 0
    assert guide.handle_response("stop") == STOPPED  # Controls work even with the model bypassed.
    assert guide.snapshot()["state"] == "stopped"
    assert guide.handle_response("ready") == STOPPED


def test_model_output_can_only_pick_an_intent_and_a_vetted_encouragement():
    assert validated_step_interpretation({"intent": "ready"}) == StepInterpretation()
    assert validated_step_interpretation(StepInterpretation("advance_two_steps")) == StepInterpretation()
    kept = validated_step_interpretation(StepInterpretation("ready", "You're doing really well, there's no rush."))
    assert kept.acknowledgment == "You're doing really well, there's no rush."
    dropped = validated_step_interpretation(StepInterpretation("ready", "Now tap the red button at the top."))
    assert dropped == StepInterpretation("ready", None)

    guide = GaitWalkthroughGuide(interpreter=FixedInterpreter(
        StepInterpretation("ready", "Great, you're doing well."),
        StepInterpretation("ready", "Now press the green arrow and then swipe left."),
    ))
    guide.start()
    assert guide.handle_response("okay my daughter opened it") == f"Great, you're doing well. {WALKTHROUGH_STEPS[1].instruction}"
    assert guide.handle_response("we're in the hall now") == f"Lovely, well done. {WALKTHROUGH_STEPS[2].instruction}"


def test_interpreter_failures_and_oversized_transcripts_count_as_unclear():
    class Broken:
        def interpret(self, transcript, step):
            raise RuntimeError("provider down")

    guide = GaitWalkthroughGuide(interpreter=Broken())
    guide.start()
    assert guide.handle_response("ready").endswith(WALKTHROUGH_STEPS[0].instruction)
    assert guide.snapshot()["help_attempts"] == 1
    guide = GaitWalkthroughGuide()
    guide.start()
    guide.handle_response("ready " * 400)
    assert guide.snapshot()["step_index"] == 0


def test_openai_walkthrough_interpreter_sends_only_the_step_and_transcript_and_validates_output():
    client = Mock()
    choice = Mock(finish_reason="stop")
    choice.message.refusal = None
    choice.message.content = '{"intent": "trouble", "acknowledgment": "Tap the top right corner now."}'
    client.chat.completions.create.return_value = Mock(choices=[choice])
    interpreter = OpenAIWalkthroughInterpreter(client)
    result = interpreter.interpret("the message never showed up on my phone", WALKTHROUGH_STEPS[0])
    assert result == StepInterpretation("trouble", None)
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["store"] is False
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    assert "open_link" in kwargs["messages"][1]["content"]
    # Whole-utterance phrases never spend a model call.
    assert interpreter.interpret("ready", WALKTHROUGH_STEPS[0]) == StepInterpretation("ready")
    assert client.chat.completions.create.call_count == 1
    client.chat.completions.create.side_effect = RuntimeError("timeout")
    assert interpreter.interpret("um so what now", WALKTHROUGH_STEPS[0]) == StepInterpretation()


def test_build_walkthrough_interpreter_is_offline_without_a_client():
    assert type(build_walkthrough_interpreter()).__name__ == "ExactWalkthroughInterpreter"
    assert isinstance(build_walkthrough_interpreter(Mock()), OpenAIWalkthroughInterpreter)


def test_call_moves_from_a_completed_survey_into_the_walkthrough():
    call = finished_survey()
    assert call.phase == "survey"
    assert call.snapshot()["call_state"] == "survey"
    assert call.snapshot()["walkthrough"] is None
    assert call.handoff is None
    prompt, answer = call.handle_response("mild")
    assert answer is not None and answer.confirmed
    assert prompt == f"{speech.COMPLETE} {TRANSITION} {WALKTHROUGH_STEPS[0].instruction}"
    snapshot = call.snapshot()
    assert snapshot["state"] == "complete"  # The survey layer is untouched.
    assert len(snapshot["answers"]) == 6
    assert snapshot["phase"] == "walkthrough"
    assert snapshot["call_state"] == "walkthrough"
    assert snapshot["walkthrough"]["current_step"] == "open_link"
    assert snapshot["gait_handoff"] == {"status": "prepared", "condition_category": "orthopedic"}
    assert "http" not in prompt  # The link is never spoken.


def test_walkthrough_turns_never_touch_survey_answers_and_finish_the_call():
    call = finished_survey()
    call.handle_response("mild")
    for reply in ("it's open", "I'm there", "ready", "all done"):
        prompt, answer = call.handle_response(reply)
        assert answer is None
    assert prompt == CONGRATULATIONS
    snapshot = call.snapshot()
    assert snapshot["call_state"] == "complete"
    assert snapshot["state"] == "complete"
    assert [a["normalized_value"] for a in snapshot["answers"]] == ["mild"] * 6
    assert call.handle_response("hello?")[0] == CONGRATULATIONS


def test_stopped_or_escalated_survey_never_starts_the_video_part():
    call = CheckUpCall(InMemoryPatientRepository(), "RGN-0417")
    call.start()
    prompt, _ = call.handle_response("stop")
    assert prompt == speech.STOPPED
    assert call.phase == "survey"
    assert call.snapshot()["call_state"] == "stopped"
    assert call.handoff is None
    assert call.handle_response("ready")[0] == speech.STOPPED


def test_walkthrough_pause_stop_and_escalation_end_or_hold_the_whole_call():
    call = finished_survey()
    call.handle_response("mild")
    assert call.handle_response("not yet")[0] == WAITING
    assert call.snapshot()["call_state"] == "walkthrough"
    assert call.handle_response("stop")[0] == STOPPED
    assert call.snapshot()["call_state"] == "stopped"

    call = finished_survey()
    call.handle_response("mild")
    for _ in range(MAX_HELP_ATTEMPTS):
        prompt, _ = call.handle_response("I can't find it")
    assert prompt == REVIEW
    assert call.snapshot()["call_state"] == "escalated"
    assert call.snapshot()["walkthrough"]["needs_human_review"] is True
