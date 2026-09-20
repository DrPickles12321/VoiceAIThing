import json
from unittest.mock import Mock

from app import conversation_policy as speech
from app.call_flow import CheckUpCall
from app.gait_walkthrough import (
    COMPANION_INSTRUCTIONS,
    CONGRATULATIONS,
    MAX_STALLED_TURNS,
    REVIEW,
    STOPPED,
    TRANSITION,
    WALKTHROUGH_STEPS,
    CompanionTurn,
    GaitWalkthroughGuide,
    OpenAIWalkthroughCompanion,
    ScriptedWalkthroughCompanion,
    build_walkthrough_companion,
    validated_turn,
)
from app.patient_repository import InMemoryPatientRepository


def finished_survey(**kwargs) -> CheckUpCall:
    call = CheckUpCall(InMemoryPatientRepository(), "RGN-0417", **kwargs)
    call.start()
    for _ in range(5):
        call.handle_response("mild")
    return call


class FakeCompanion:
    """Stands in for the model: returns scripted turns and records what it was shown."""

    def __init__(self, *turns):
        self.turns = iter(turns)
        self.calls = []

    def respond(self, transcript, steps, step_index, history):
        self.calls.append({"transcript": transcript, "step": steps[step_index].id, "history": list(history)})
        return next(self.turns)


def model_client(*payloads):
    client = Mock()
    choices = []
    for payload in payloads:
        choice = Mock(finish_reason="stop")
        choice.message.refusal = None
        choice.message.content = json.dumps(payload) if isinstance(payload, dict) else payload
        choices.append(Mock(choices=[choice]))
    client.chat.completions.create.side_effect = choices
    return client


def test_opening_is_fixed_and_the_companion_speaks_for_every_later_turn():
    companion = FakeCompanion(
        CompanionTurn("stay", "Hello Margaret, lovely to keep chatting. Do you see a new text message on your phone?"),
        CompanionTurn("advance", "Wonderful, that's it open. Now, is there a hallway or clear bit of floor nearby where you could take about ten steps in a straight line? Somewhere with good light. Tell me when you're there."),
    )
    guide = GaitWalkthroughGuide(companion=companion)
    assert guide.start() == f"{TRANSITION} {WALKTHROUGH_STEPS[0].instruction}"
    first = guide.handle_response("Oh hello dear, my name is Margaret, my daughter is just fetching the phone")
    assert first.startswith("Hello Margaret")
    assert guide.snapshot()["current_step"] == "open_link"
    second = guide.handle_response("Right, she's tapped it and there's a page with a big picture of a camera")
    assert second.startswith("Wonderful, that's it open.")
    assert guide.snapshot()["current_step"] == "find_space"
    assert guide.snapshot()["stalled_turns"] == 0
    # The companion sees the whole walkthrough so far, not just the last line.
    assert companion.calls[1]["step"] == "open_link"
    assert [turn["role"] for turn in companion.calls[1]["history"]] == ["assistant", "user", "assistant"]
    assert companion.calls[1]["history"][1]["content"].startswith("Oh hello dear")


def test_the_guide_moves_at_most_one_step_per_turn_and_owns_the_ending():
    companion = FakeCompanion(*[CompanionTurn("advance", "Great, on to the next bit.")] * 3 + [CompanionTurn("advance", "")])
    guide = GaitWalkthroughGuide(companion=companion)
    guide.start()
    for expected in ("find_space", "place_phone", "record_walk"):
        guide.handle_response("done, what's next, and the one after that too")
        assert guide.snapshot()["current_step"] == expected
    assert guide.handle_response("finished walking") == CONGRATULATIONS  # Empty reply -> fixed closing.
    assert guide.snapshot()["state"] == "complete"
    assert guide.snapshot()["current_step"] is None
    assert guide.handle_response("hello?") == CONGRATULATIONS


def test_stay_keeps_the_step_and_a_long_stall_hands_over_to_a_person():
    companion = FakeCompanion(*[CompanionTurn("stay", "No rush at all, take your time.")] * MAX_STALLED_TURNS)
    guide = GaitWalkthroughGuide(companion=companion)
    guide.start()
    for attempt in range(1, MAX_STALLED_TURNS):
        assert guide.handle_response("still looking") == "No rush at all, take your time."
        assert guide.snapshot()["stalled_turns"] == attempt
        assert guide.snapshot()["current_step"] == "open_link"
    assert guide.handle_response("still nothing") == REVIEW
    assert guide.snapshot()["state"] == "escalated"
    assert guide.snapshot()["needs_human_review"] is True


def test_stop_and_escalate_end_the_call_with_the_companion_words_when_valid():
    guide = GaitWalkthroughGuide(companion=FakeCompanion(CompanionTurn("stop", "Of course, we'll leave it there. Bye for now.")))
    guide.start()
    assert guide.handle_response("I think I've had enough for today thank you") == "Of course, we'll leave it there. Bye for now."
    assert guide.snapshot()["state"] == "stopped"

    guide = GaitWalkthroughGuide(companion=FakeCompanion(CompanionTurn("escalate", None)))
    guide.start()
    assert guide.handle_response("I feel dizzy and I'm frightened to walk") == REVIEW
    assert guide.snapshot()["state"] == "escalated"
    assert guide.snapshot()["needs_human_review"] is True


def test_a_plain_spoken_stop_never_reaches_the_model():
    companion = FakeCompanion()  # Any call would raise StopIteration.
    guide = GaitWalkthroughGuide(companion=companion)
    guide.start()
    assert guide.handle_response("stop please") == STOPPED
    assert companion.calls == []
    assert guide.snapshot()["state"] == "stopped"


def test_invalid_model_output_falls_back_to_the_fixed_script():
    assert validated_turn({"action": "advance", "reply": "x"}) == CompanionTurn()
    assert validated_turn(CompanionTurn("skip_to_end", "hi")) == CompanionTurn()
    assert validated_turn(CompanionTurn("stay", "Tap the link at www.example.com to continue.")) == CompanionTurn("stay", None)
    assert validated_turn(CompanionTurn("stay", "word " * 91)) == CompanionTurn("stay", None)
    assert validated_turn(CompanionTurn("stay", "  Take   your time.  ")) == CompanionTurn("stay", "Take your time.")

    class Broken:
        def respond(self, *args):
            raise RuntimeError("provider down")

    guide = GaitWalkthroughGuide(companion=Broken())
    guide.start()
    prompt = guide.handle_response("okay it's open now")
    assert prompt.endswith(WALKTHROUGH_STEPS[0].instruction)
    assert guide.snapshot()["stalled_turns"] == 1
    guide = GaitWalkthroughGuide(companion=FakeCompanion(CompanionTurn("advance", "Visit http://evil.example to continue")))
    guide.start()
    assert guide.handle_response("it's open") == f"Lovely, well done. {WALKTHROUGH_STEPS[1].instruction}"


def test_openai_companion_sends_instructions_context_and_history_and_validates_output():
    client = model_client(
        {"action": "stay", "reply": "That's alright, Margaret. Have a look in your messages app; is there a new text from the clinic?"},
        '{"action": "advance", "reply": "Perfect.", "extra": true}',
    )
    companion = OpenAIWalkthroughCompanion(client, model="test-model")
    history = [{"role": "assistant", "content": "First, a text message..."}]
    turn = companion.respond("I don't see any message, dear", WALKTHROUGH_STEPS, 0, history)
    assert turn.action == "stay"
    assert turn.reply.startswith("That's alright, Margaret.")
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "test-model"
    assert kwargs["store"] is False
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    assert kwargs["messages"][0] == {"role": "system", "content": COMPANION_INSTRUCTIONS}
    context = json.loads(kwargs["messages"][1]["content"].split("\n", 1)[1])
    assert context["current_step"]["id"] == "open_link"
    assert context["next_step"]["id"] == "find_space"
    assert context["is_last_step"] is False
    assert kwargs["messages"][2] == history[0]
    assert kwargs["messages"][-1] == {"role": "user", "content": "I don't see any message, dear"}
    # Unexpected keys are rejected rather than trusted.
    assert companion.respond("ok", WALKTHROUGH_STEPS, 0, history) == CompanionTurn()
    client.chat.completions.create.side_effect = RuntimeError("timeout")
    assert companion.respond("ok", WALKTHROUGH_STEPS, 3, history) == CompanionTurn()


def test_last_step_context_has_no_next_step():
    client = model_client({"action": "advance", "reply": "You did it, well done."})
    OpenAIWalkthroughCompanion(client).respond("all done", WALKTHROUGH_STEPS, len(WALKTHROUGH_STEPS) - 1, [])
    context = json.loads(client.chat.completions.create.call_args.kwargs["messages"][1]["content"].split("\n", 1)[1])
    assert context["next_step"] is None
    assert context["is_last_step"] is True


def test_companion_prompt_states_the_boundaries():
    for phrase in ("medical", "artificial intelligence", "tracking", "web address", "not commands"):
        assert phrase in COMPANION_INSTRUCTIONS


def test_without_a_client_the_scripted_companion_is_only_a_degraded_fallback():
    assert isinstance(build_walkthrough_companion(), ScriptedWalkthroughCompanion)
    assert isinstance(build_walkthrough_companion(Mock()), OpenAIWalkthroughCompanion)
    guide = GaitWalkthroughGuide()
    guide.start()
    assert guide.handle_response("ready").endswith(WALKTHROUGH_STEPS[1].instruction)
    assert guide.handle_response("um my daughter opened it I think").endswith(WALKTHROUGH_STEPS[1].instruction)
    assert guide.snapshot()["current_step"] == "find_space"


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
    companion = FakeCompanion(*[CompanionTurn("advance", "Lovely, next bit.")] * 3, CompanionTurn("advance", "All done, thank you so much."))
    call = finished_survey(walkthrough_companion=companion)
    call.handle_response("mild")
    for reply in ("we've got it open", "I'm in the hallway now", "it's leaning on the chair", "I walked there and back"):
        prompt, answer = call.handle_response(reply)
        assert answer is None
    assert prompt == "All done, thank you so much."
    snapshot = call.snapshot()
    assert snapshot["call_state"] == "complete"
    assert snapshot["state"] == "complete"
    assert [a["normalized_value"] for a in snapshot["answers"]] == ["mild"] * 6
    assert call.handle_response("hello?")[0] == CONGRATULATIONS
    # Survey content is not shown to the walkthrough companion.
    assert all("mild" not in turn["content"] for turn in companion.calls[0]["history"])


def test_stopped_or_escalated_survey_never_starts_the_video_part():
    call = CheckUpCall(InMemoryPatientRepository(), "RGN-0417")
    call.start()
    prompt, _ = call.handle_response("stop")
    assert prompt == speech.STOPPED
    assert call.phase == "survey"
    assert call.snapshot()["call_state"] == "stopped"
    assert call.handoff is None
    assert call.handle_response("ready")[0] == speech.STOPPED


def test_walkthrough_stop_and_escalation_end_the_whole_call():
    call = finished_survey(walkthrough_companion=FakeCompanion(CompanionTurn("stay", "Take your time."), CompanionTurn("stop", None)))
    call.handle_response("mild")
    assert call.handle_response("hang on")[0] == "Take your time."
    assert call.snapshot()["call_state"] == "walkthrough"
    assert call.handle_response("no I'd rather not do this today")[0] == STOPPED
    assert call.snapshot()["call_state"] == "stopped"

    call = finished_survey(walkthrough_companion=FakeCompanion(CompanionTurn("escalate", "I'll ask the clinic to help you with this another day.")))
    call.handle_response("mild")
    prompt, _ = call.handle_response("I can't manage this, can a person ring me")
    assert prompt == "I'll ask the clinic to help you with this another day."
    assert call.snapshot()["call_state"] == "escalated"
    assert call.snapshot()["walkthrough"]["needs_human_review"] is True
