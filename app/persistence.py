from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CallRecord:
    session_id: str
    patient_code: str
    condition_category: str
    transcript: list[str] = field(default_factory=list)
    status: str = "in_progress"
    answers: list[dict[str, object]] = field(default_factory=list)
    final_status: str | None = None
    call_sid: str | None = None
    to_number: str | None = None
    carrier_status: str | None = None


class InMemoryPersistence:
    """Persistence bridge for the safe runtime; replaceable with Supabase later."""

    def __init__(self):
        self.calls: dict[str, CallRecord] = {}

    def start_call(self, session_id: str, patient_code: str, condition_category: str) -> CallRecord:
        existing = self.calls.get(session_id)
        if existing is not None:
            return existing
        record = CallRecord(
            session_id=session_id,
            patient_code=patient_code,
            condition_category=condition_category,
        )
        self.calls[session_id] = record
        return record

    def append_transcript(self, session_id: str, text: str) -> None:
        record = self.calls.get(session_id)
        if record is not None:
            record.transcript.append(text)

    def record_answer(self, session_id: str, answer: dict[str, object]) -> None:
        record = self.calls.get(session_id)
        if record is not None:
            record.answers.append(answer)

    def complete_call(self, session_id: str, final_status: str = "completed") -> CallRecord:
        record = self.calls[session_id]
        record.status = "completed"
        record.final_status = final_status
        return record
