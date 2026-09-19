from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


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
        intro = (
            "Hello, this is your care team. I’m going to ask a few short questions "
            f"about your {condition_category} recovery and then we’ll send a link for follow-up."
        )
        return VoiceTurn("assistant", self.tts(intro))

    def ask_question(self, question_prompt: str) -> VoiceTurn:
        return VoiceTurn("assistant", self.tts(question_prompt))

    def confirmation_prompt(self, confirmation_text: str) -> VoiceTurn:
        return VoiceTurn("assistant", self.tts(confirmation_text))

    def closing_script(self) -> VoiceTurn:
        script = (
            "Thank you so much for your time today. We’ll send you a link shortly to complete "
            "a quick recording for the gait tracker."
        )
        return VoiceTurn("assistant", self.tts(script))

    def normalize_input(self, transcript: str) -> str:
        return self.stt(transcript).strip()
