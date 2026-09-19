from __future__ import annotations

from collections.abc import Callable
import re

from .models import Extraction, SurveyQuestion

Extractor = Callable[[str, SurveyQuestion], Extraction]


class ExtractionError(Exception):
    """Expected provider failure; no candidate may be saved."""


def keyword_extractor(text: str, question: SurveyQuestion) -> Extraction:
    """Match an explicit option, ignoring surrounding whitespace/end punctuation.

    Preserve internal wording and the original evidence. Free-form statements,
    negations, corrections and multiple choices require clarification offline.
    Use the LLM adapter for semantic interpretation.
    """
    normalized = re.sub(r"[\s.!?]+$", "", text.casefold().strip())
    matches = [option for option in question.options if option.casefold() == normalized]
    if len(matches) == 1:
        return Extraction(question.id, matches[0], 0.99, text)
    return Extraction(question.id, None, 0.0, text, needs_clarification=True)
