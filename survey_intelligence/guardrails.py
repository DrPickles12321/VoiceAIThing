from __future__ import annotations

from .models import SafetyFlag

# Demo-only conservative phrases. Replace with a clinician-reviewed policy.
ESCALATION_PHRASES = (
    "can't breathe", "chest pain", "fainted", "passed out", "sudden swelling",
    "severe bleeding", "barely move", "call an ambulance",
)


def detect_safety_flag(text: str) -> SafetyFlag | None:
    normalized = text.casefold()
    for phrase in ESCALATION_PHRASES:
        if phrase in normalized:
            return SafetyFlag(reason="potential_urgent_symptom", evidence=phrase)
    return None
