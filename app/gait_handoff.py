from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GaitHandoff:
    patient_code: str
    condition_category: str
    status: str = "prepared"
    link: str | None = None
    notes: list[str] = field(default_factory=list)


class GaitHandoffService:
    """Prepare the handoff payload without performing real remote delivery.

    This intentionally keeps link generation and transport in a later repo or
    integration boundary. This service only prepares the payload and status.
    """

    def __init__(self, link_generator=None):
        self.link_generator = link_generator or (lambda patient_code, condition_category: f"https://gait.example/{patient_code}/{condition_category}")

    def prepare(self, patient_code: str, condition_category: str) -> GaitHandoff:
        handoff = GaitHandoff(
            patient_code=patient_code,
            condition_category=condition_category,
        )
        handoff.link = self.link_generator(patient_code, condition_category)
        handoff.notes.append("Handoff prepared for gait-checker integration.")
        return handoff
