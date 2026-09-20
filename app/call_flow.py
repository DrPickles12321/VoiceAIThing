"""One check-up call: the survey first, then the gait video walkthrough.

Each layer keeps its own guardrails. The survey engine still ends in its own
``complete`` state and the walkthrough only begins after that; a stopped or
escalated survey never continues into the video step.
"""

from __future__ import annotations

from .gait_handoff import GaitHandoff, GaitHandoffService
from .gait_walkthrough import GaitWalkthroughGuide, WalkthroughCompanion
from .models import SurveyAnswer
from .survey_engine import SafeSurveyEngine

CALL_TERMINAL_STATES = {"complete", "stopped", "escalated"}


class CheckUpCall:
    def __init__(
        self,
        repository,
        patient_code: str,
        interpreter=None,
        walkthrough_companion: WalkthroughCompanion | None = None,
        handoff_service: GaitHandoffService | None = None,
    ):
        self.survey = SafeSurveyEngine(repository, patient_code, interpreter=interpreter)
        self.walkthrough = GaitWalkthroughGuide(companion=walkthrough_companion)
        self.handoff_service = handoff_service or GaitHandoffService()
        self.handoff: GaitHandoff | None = None
        self.phase = "survey"

    @property
    def patient(self):
        return self.survey.patient

    @property
    def call_state(self) -> str:
        if self.phase == "survey":
            state = self.survey.session.state
            return state if state in {"stopped", "escalated"} else "survey"
        state = self.walkthrough.state
        return state if state in CALL_TERMINAL_STATES else "walkthrough"

    def _after_survey(self, prompt: str) -> str:
        if self.phase == "survey" and self.survey.session.state == "complete":
            self.phase = "walkthrough"
            patient = self.patient
            # Prepared only; the link is never spoken or delivered from here.
            self.handoff = self.handoff_service.prepare(patient.patient_code, patient.condition_category.value)
            prompt = f"{prompt} {self.walkthrough.start()}"
        return prompt

    def start(self) -> str:
        if self.phase == "survey":
            return self._after_survey(self.survey.start())
        return self.walkthrough.start()

    def handle_response(self, transcript: str) -> tuple[str, SurveyAnswer | None]:
        if self.phase == "survey":
            prompt, answer = self.survey.handle_response(transcript)
            return self._after_survey(prompt), answer
        return self.walkthrough.handle_response(transcript), None

    def snapshot(self) -> dict[str, object]:
        return {
            **self.survey.snapshot(),
            "phase": self.phase,
            "call_state": self.call_state,
            "walkthrough": self.walkthrough.snapshot() if self.phase == "walkthrough" else None,
            "gait_handoff": {
                "status": self.handoff.status, "condition_category": self.handoff.condition_category,
            } if self.handoff else None,
        }
