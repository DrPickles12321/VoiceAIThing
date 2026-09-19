"""In-process backend boundary; a FastAPI route can call these methods.

Storage is intentionally in-memory. For multiple workers replace it with a
transactional session store. Call synchronous methods in a worker thread.
"""
from threading import RLock
from uuid import uuid4

from .engine import SurveyEngine


class SurveyService:
    def __init__(self, survey, extractor):
        self.survey = survey
        self.extractor = extractor
        self._sessions = {}
        self._lock = RLock()

    def create_session(self):
        engine = SurveyEngine(self.survey, self.extractor)
        prompt = engine.start()
        session_id = str(uuid4())
        with self._lock:
            self._sessions[session_id] = (engine, RLock())
        return {"session_id": session_id, "prompt": prompt, **engine.snapshot()}

    def handle_turn(self, session_id: str, transcript: str):
        with self._lock:
            engine, lock = self._sessions[session_id]
        with lock:
            prompt = engine.handle_turn(transcript)
            return {"session_id": session_id, "prompt": prompt, **engine.snapshot()}
