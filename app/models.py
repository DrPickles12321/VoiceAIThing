from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class ConditionCategory(str, Enum):
    ORTHOPEDIC = "orthopedic"
    STROKE = "stroke"


@dataclass(frozen=True)
class PatientRecord:
    patient_id: str
    patient_code: str
    condition_category: ConditionCategory


@dataclass(frozen=True)
class SurveyQuestion:
    id: str
    prompt: str
    answer_options: tuple[str, ...]
    topic: str
    condition_category: ConditionCategory
    domain: str


@dataclass
class SurveyAnswer:
    question_id: str
    question_prompt: str
    normalized_value: str
    raw_response: str
    confidence: float
    confirmed: bool = False
    clarification_attempts: int = 0


@dataclass
class SurveySession:
    patient: PatientRecord
    questions: tuple[SurveyQuestion, ...]
    state: str = "awaiting_start"
    current_index: int = 0
    answers: list[SurveyAnswer] = field(default_factory=list)
    last_confirmation_prompt: str | None = None
    clarification_attempts: int = 0
    needs_human_review: bool = False

    @property
    def current_question(self) -> SurveyQuestion | None:
        if self.current_index >= len(self.questions):
            return None
        return self.questions[self.current_index]

    @property
    def is_complete(self) -> bool:
        return self.current_index >= len(self.questions)


def normalize_answer(value: str, options: Iterable[str]) -> str | None:
    cleaned = value.strip().casefold().rstrip(".!?")
    for option in options:
        if option.casefold() == cleaned:
            return option.casefold()
    return None
