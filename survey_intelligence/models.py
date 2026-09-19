from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SurveyState(str, Enum):
    ASKING = "asking"
    LISTENING = "listening"
    INTERPRETING = "interpreting"
    CLARIFYING = "clarifying"
    CONFIRMING = "confirming"
    SAVING = "saving"
    COMPLETE = "complete"
    ESCALATED = "escalated"
    STOPPED = "stopped"


@dataclass(frozen=True)
class SurveyQuestion:
    id: str
    prompt: str
    options: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True)
class SurveyDefinition:
    id: str
    questions: tuple[SurveyQuestion, ...]
    title: str = ""
    instructions: str = ""


@dataclass(frozen=True)
class Extraction:
    question_id: str
    value: str | None
    confidence: float | None
    evidence: str
    needs_clarification: bool = False


@dataclass(frozen=True)
class SafetyFlag:
    reason: str
    evidence: str


@dataclass
class ConfirmedResponse:
    question_id: str
    value: str
    raw_response: str
    evidence: str
    confidence: float | None
    confirmation_transcript: str = ""


@dataclass
class SurveySession:
    survey: SurveyDefinition
    state: SurveyState = SurveyState.ASKING
    question_index: int = 0
    pending_extraction: Extraction | None = None
    pending_transcript: str | None = None
    responses: dict[str, ConfirmedResponse] = field(default_factory=dict)
    safety_flags: list[SafetyFlag] = field(default_factory=list)

    @property
    def current_question(self) -> SurveyQuestion | None:
        return self.survey.questions[self.question_index] if self.question_index < len(self.survey.questions) else None
