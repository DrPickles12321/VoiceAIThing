from __future__ import annotations

from .extractor import Extractor, keyword_extractor
from .guardrails import detect_safety_flag
from .models import ConfirmedResponse, SurveyDefinition, SurveySession, SurveyState


class SurveyEngine:
    """Owns progression, validation, confirmation, persistence, and escalation."""

    def __init__(self, survey: SurveyDefinition, extractor: Extractor = keyword_extractor) -> None:
        self.session = SurveySession(survey=survey)
        self.extractor = extractor

    def start(self) -> str:
        question = self.session.current_question
        if question is None:
            self.session.state = SurveyState.COMPLETE
            return "Survey complete."
        self.session.state = SurveyState.LISTENING
        return question.prompt

    def receive_transcript(self, transcript: str) -> str:
        if self.session.state in (SurveyState.COMPLETE, SurveyState.ESCALATED):
            raise RuntimeError(f"Cannot receive input in {self.session.state.value} state.")
        flag = detect_safety_flag(transcript)
        if flag:
            self.session.safety_flags.append(flag)
            self.session.state = SurveyState.ESCALATED
            return "Thank you for telling me. I’m going to flag this for your care team rather than interpret it as a survey response."
        question = self.session.current_question
        if question is None:
            self.session.state = SurveyState.COMPLETE
            return "Survey complete."
        self.session.state = SurveyState.INTERPRETING
        extraction = self.extractor(transcript, question)
        self.session.pending_extraction = extraction
        if extraction.question_id != question.id or extraction.value not in question.options:
            self.session.state = SurveyState.CLARIFYING
            return f"Please answer using one of: {', '.join(question.options)}."
        if extraction.needs_clarification or extraction.confidence < 0.70:
            self.session.state = SurveyState.CLARIFYING
            return f"Could you say whether you would describe it as {', '.join(question.options)}?"
        self.session.state = SurveyState.CONFIRMING
        return f"It sounds like you would describe it as {extraction.value}. Is that right? Please say yes or no."

    def confirm(self, answer: str, raw_transcript: str) -> str:
        if self.session.state != SurveyState.CONFIRMING:
            raise RuntimeError("Confirmation is only valid after a candidate extraction.")
        normalized = answer.strip().casefold()
        if normalized in {"yes", "yeah", "yep", "correct", "that's right"}:
            extraction = self.session.pending_extraction
            assert extraction is not None
            question = self.session.current_question
            assert question is not None
            self.session.state = SurveyState.SAVING
            self.session.responses[question.id] = ConfirmedResponse(
                question.id, extraction.value or "", raw_transcript, extraction.evidence, extraction.confidence
            )
            self.session.pending_extraction = None
            self.session.question_index += 1
            if self.session.current_question is None:
                self.session.state = SurveyState.COMPLETE
                return "Thank you. The survey is complete."
            self.session.state = SurveyState.LISTENING
            return self.session.current_question.prompt
        if normalized in {"no", "nope", "incorrect", "not right"}:
            self.session.pending_extraction = None
            self.session.state = SurveyState.LISTENING
            return "Thanks for correcting me. Please answer the question again."
        return "Please say yes if that is correct, or no if I should try again."

    def snapshot(self) -> dict[str, object]:
        return {
            "state": self.session.state.value,
            "current_question": self.session.current_question.id if self.session.current_question else None,
            "responses": {
                key: {"value": value.value, "raw_response": value.raw_response, "evidence": value.evidence, "confirmed": True}
                for key, value in self.session.responses.items()
            },
            "safety_flags": [{"reason": flag.reason, "evidence": flag.evidence} for flag in self.session.safety_flags],
        }
