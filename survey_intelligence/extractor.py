from __future__ import annotations

from collections.abc import Callable

from .models import Extraction, SurveyQuestion

Extractor = Callable[[str, SurveyQuestion], Extraction]


class ExtractionError(Exception):
    """Expected provider failure; no candidate may be saved."""


def keyword_extractor(text: str, question: SurveyQuestion) -> Extraction:
    """Deterministic demo extractor; replace with a structured LLM adapter."""
    normalized = text.casefold()
    matches = [option for option in question.options if option.casefold() == normalized.strip().rstrip('.!?')]
    if len(matches) == 1:
        return Extraction(question.id, matches[0], 0.99, text)
    if question.id == "stairs" and not any(word in normalized for word in ("not", "no ", "but")) and any(
        phrase in normalized for phrase in ("hold onto the railing", "pull myself up", "terrible")
    ):
        return Extraction(question.id, "severe", 0.88, text)
    return Extraction(question.id, None, 0.0, text, needs_clarification=True)
