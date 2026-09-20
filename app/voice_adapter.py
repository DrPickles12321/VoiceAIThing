from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .conversation_policy import COMPLETE, INTRO


@dataclass(frozen=True)
class VoiceTurn:
    speaker: str
    text: str


class VoiceAdapter:
    """Thin boundary for speech-to-text and text-to-speech integration.

    The adapter is intentionally simple: it only standardizes the conversation flow
    and keeps the AI logic decoupled from any specific provider. This repo does not
    implement a live telephony stack yet; it only prepares the interaction contract.
    """

    def __init__(self, tts: Callable[[str], str] | None = None, stt: Callable[[str], str] | None = None):
        self.tts = tts or (lambda text: text)
        self.stt = stt or (lambda text: text)

    def doctor_intro(self, condition_category: str) -> VoiceTurn:
        """Compatibility entry point; a real doctor's recording is a separate asset."""
        return VoiceTurn("assistant", self.tts(INTRO))

    def ask_question(self, question_prompt: str) -> VoiceTurn:
        return VoiceTurn("assistant", self.tts(question_prompt))

    def confirmation_prompt(self, confirmation_text: str) -> VoiceTurn:
        return VoiceTurn("assistant", self.tts(confirmation_text))

    def closing_script(self) -> VoiceTurn:
        return VoiceTurn("assistant", self.tts(COMPLETE))

    def normalize_input(self, transcript: str) -> str:
        return self.stt(transcript).strip()
