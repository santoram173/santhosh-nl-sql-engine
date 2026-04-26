"""Session Store — in-memory, per-user, isolated."""
from __future__ import annotations
import logging
from collections import defaultdict, deque
from typing import Any, Optional
from backend.config import get_settings

log = logging.getLogger(__name__)


class SessionStore:
    _instance: Optional["SessionStore"] = None

    def __init__(self):
        cfg = get_settings()
        self._max_history = cfg.session_max_history
        # session_id → deque of interaction dicts
        self._store: dict[str, deque] = defaultdict(lambda: deque(maxlen=self._max_history))

    @classmethod
    def get_instance(cls) -> "SessionStore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def add_interaction(self, session_id: str, data: dict[str, Any]) -> None:
        self._store[session_id].append(data)

    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        return list(self._store[session_id])

    def clear(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    def session_info(self, session_id: str) -> dict:
        history = self.get_history(session_id)
        return {
            "session_id": session_id,
            "history_count": len(history),
            "history": history,
        }

    def active_sessions(self) -> int:
        return len(self._store)
