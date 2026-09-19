from __future__ import annotations

from .models import SurveyAnswer, SurveySession, normalize_answer
from .question_loader import load_question_bank


class SafeSurveyEngine:
    """Minimal survey loop with explicit patient lookup and bounded confirmation."""

    def __init__(self, repository, patient_code: str):
        self.repository = repository
        self.patient = repository.lookup_patient(patient_code)
        self.session = SurveySession(
            patient=self.patient,
            questions=load_question_bank(self.patient.condition_category),
        )

    def start(self) -> str:
        if self.session.current_question is None:
            self.session.state = "complete"
            return "Survey complete."
        self.session.state = "asking"
        question = self.session.current_question
        return (
            "HOOS JR HIP SURVEY\n"
            f"Condition: {self.patient.condition_category.value}\n"
            f"Question {self.session.current_index + 1} of {len(self.session.questions)}\n"
            f"{question.prompt}"
        )

    def _confirmation_prompt(self, question, normalized_value: str) -> str:
        return f"You said your {question.topic} was {normalized_value}, correct?"

    def handle_response(self, transcript: str) -> tuple[str, SurveyAnswer | None]:
        question = self.session.current_question
        if question is None:
            self.session.state = "complete"
            return ("Survey complete.", None)

        if self.session.state == "awaiting_confirmation":
            normalized = transcript.strip().casefold().rstrip(".!?")
            if normalized in {"yes", "yeah", "yep", "correct"}:
                answer = self.session.answers[-1]
                answer.confirmed = True
                self.session.current_index += 1
                self.session.state = "asking"
                if self.session.current_question is None:
                    self.session.state = "complete"
                    return ("Thank you. The survey is complete.", answer)
                next_question = self.session.current_question
                return (
                    f"Next question: {next_question.prompt}",
                    answer,
                )
            if normalized in {"no", "nope", "not correct"}:
                self.session.state = "asking"
                return (f"Thanks for correcting me. {question.prompt}", None)
            self.session.clarification_attempts += 1
            if self.session.clarification_attempts >= 3:
                self.session.needs_human_review = True
                self.session.state = "escalated"
                return ("I’m unable to confirm this answer reliably. A clinician will review it manually.", None)
            return ("Please answer yes or no to confirm your selection.", None)

        normalized_value = normalize_answer(transcript, question.answer_options)
        if normalized_value is None:
            self.session.state = "clarifying"
            self.session.clarification_attempts += 1
            if self.session.clarification_attempts >= 3:
                self.session.needs_human_review = True
                self.session.state = "escalated"
                return ("I’m not confident in the answer I heard. A clinician will review this manually.", None)
            options = ", ".join(question.answer_options)
            return (f"I could not interpret that. Please choose one of: {options}.", None)

        self.session.clarification_attempts = 0
        answer = SurveyAnswer(
            question_id=question.id,
            question_prompt=question.prompt,
            normalized_value=normalized_value,
            raw_response=transcript,
            confidence=0.99,
            confirmed=False,
            clarification_attempts=0,
        )
        self.session.answers.append(answer)
        self.session.state = "awaiting_confirmation"
        self.session.last_confirmation_prompt = self._confirmation_prompt(question, normalized_value)
        return (self.session.last_confirmation_prompt, answer)

    def snapshot(self) -> dict[str, object]:
        return {
            "patient_code": self.patient.patient_code,
            "condition_category": self.patient.condition_category.value,
            "state": self.session.state,
            "current_index": self.session.current_index,
            "current_question": self.session.current_question.id if self.session.current_question else None,
            "answers": [
                {
                    "question_id": answer.question_id,
                    "normalized_value": answer.normalized_value,
                    "confirmed": answer.confirmed,
                }
                for answer in self.session.answers
            ],
            "question_count": len(self.session.questions),
            "clarification_attempts": self.session.clarification_attempts,
            "needs_human_review": self.session.needs_human_review,
        }
