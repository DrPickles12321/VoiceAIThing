from __future__ import annotations

from dataclasses import asdict
import math
import re

from .extractor import Extractor, ExtractionError, keyword_extractor
from .guardrails import detect_safety_flag
from .models import ConfirmedResponse, Extraction, SurveyDefinition, SurveySession, SurveyState

TERMINAL = {SurveyState.COMPLETE, SurveyState.ESCALATED, SurveyState.STOPPED}


class SurveyEngine:
    """Single-session controller. The service serializes concurrent turns."""

    def __init__(self, survey: SurveyDefinition, extractor: Extractor = keyword_extractor):
        ids = [q.id for q in survey.questions]
        if len(set(ids)) != len(ids) or any(not q.id or not q.prompt or not q.options for q in survey.questions):
            raise ValueError("Questions require unique IDs, prompts and nonempty options.")
        self.session = SurveySession(survey=survey)
        self.extractor = extractor

    def start(self) -> str:
        if self.session.state != SurveyState.ASKING:
            raise RuntimeError("A session can only be started once.")
        question = self.session.current_question
        self.session.state = SurveyState.LISTENING if question else SurveyState.COMPLETE
        return question.prompt if question else "Survey complete."

    def _clear_pending(self):
        self.session.pending_extraction = None
        self.session.pending_transcript = None

    def _guard(self, text: str) -> str | None:
        flag = detect_safety_flag(text)
        if flag:
            self._clear_pending()
            self.session.safety_flags.append(flag)
            self.session.state = SurveyState.ESCALATED
            return "The survey is paused for review. This demo does not notify a care team."
        normalized = text.strip().casefold().rstrip(".!?")
        if normalized in {"stop", "stop the survey", "opt out", "quit", "i want to stop"}:
            self._clear_pending()
            self.session.state = SurveyState.STOPPED
            return "The survey has stopped."
        return None

    def handle_turn(self, transcript: str) -> str:
        if not isinstance(transcript, str):
            raise TypeError("Transcript must be text.")
        if self.session.state in TERMINAL:
            raise RuntimeError("This session has ended.")
        if self.session.state == SurveyState.CONFIRMING:
            return self.confirm(transcript)
        return self.receive_transcript(transcript)

    def receive_transcript(self, transcript: str) -> str:
        if self.session.state not in {SurveyState.LISTENING, SurveyState.CLARIFYING}:
            raise RuntimeError("Start the survey and resolve any pending confirmation first.")
        guarded = self._guard(transcript)
        if guarded:
            return guarded
        if not transcript.strip() or len(transcript) > 8000:
            return "Please provide a short answer to the current question."
        question = self.session.current_question
        assert question is not None
        self._clear_pending()
        self.session.state = SurveyState.INTERPRETING
        try:
            result = self.extractor(transcript, question)
        except ExtractionError:
            self.session.state = SurveyState.CLARIFYING
            return "I couldn't interpret that just now. Please repeat your answer."
        except Exception:
            self.session.state = SurveyState.CLARIFYING
            raise
        valid = (
            isinstance(result, Extraction)
            and result.question_id == question.id
            and result.value in question.options
            and result.needs_clarification is False
            and isinstance(result.evidence, str)
            and bool(result.evidence.strip())
            and result.evidence in transcript
            and (result.confidence is None or (
                type(result.confidence) in (float, int)
                and math.isfinite(result.confidence)
                and 0.7 <= result.confidence <= 1
            ))
        )
        if not valid:
            self.session.state = SurveyState.CLARIFYING
            return f"{question.prompt} Please choose: {', '.join(question.options)}."
        self.session.pending_extraction = result
        self.session.pending_transcript = transcript
        self.session.state = SurveyState.CONFIRMING
        return f"For the question '{question.prompt}', I understood '{result.value}'. Is that correct? Please say yes or no."

    def confirm(self, answer: str, raw_transcript: str | None = None) -> str:
        # Second argument retained for old callers; source provenance is internal.
        if self.session.state != SurveyState.CONFIRMING:
            raise RuntimeError("No candidate is awaiting confirmation.")
        guarded = self._guard(answer)
        if guarded:
            return guarded
        if raw_transcript is not None:
            guarded = self._guard(raw_transcript)
            if guarded:
                return guarded
        normalized = re.sub(r"[.!?,]+$", "", answer.strip().casefold()).strip()
        if raw_transcript is not None and raw_transcript != answer:
            return "Please confirm with an unmodified yes or no transcript."
        if normalized in {"yes", "yeah", "yep", "correct", "that's right"}:
            result = self.session.pending_extraction
            question = self.session.current_question
            assert result is not None and question is not None
            self.session.state = SurveyState.SAVING
            self.session.responses[question.id] = ConfirmedResponse(
                question.id, result.value, self.session.pending_transcript,
                result.evidence, result.confidence, answer,
            )
            self._clear_pending()
            self.session.question_index += 1
            question = self.session.current_question
            self.session.state = SurveyState.LISTENING if question else SurveyState.COMPLETE
            return question.prompt if question else "Thank you. The survey is complete."
        if normalized in {"no", "nope", "incorrect", "not right"}:
            self._clear_pending()
            self.session.state = SurveyState.LISTENING
            return "Thanks for correcting me. " + self.session.current_question.prompt
        return "Please say yes if that is correct, or no to change your answer."

    def snapshot(self) -> dict[str, object]:
        return {
            "state": self.session.state.value,
            "current_question": self.session.current_question.id if self.session.current_question else None,
            "responses": {key: {**asdict(value), "confirmed": True} for key, value in self.session.responses.items()},
            "safety_flags": [asdict(flag) for flag in self.session.safety_flags],
        }
