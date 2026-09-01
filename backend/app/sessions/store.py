import threading

from app.sessions.models import SessionState


class SessionStore:
    """In-memory session store, keyed by session_id. Resets on process restart.

    Lock-guarded for the reason spelled out in crm/store.py: every live call is
    its own thread, `all()` walks the dict, and a concurrent `get_or_create`
    inserting into it while the capacity endpoint or the load harness is
    reading raised "dictionary changed size during iteration" at 256 calls at
    once. The critical sections are a single dict operation each.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState | None:
        with self._lock:
            return self._sessions.get(session_id)

    def get_or_create(self, session_id: str) -> SessionState:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = SessionState(session_id=session_id, mem0_user_id=session_id)
                self._sessions[session_id] = session
            return session

    def save(self, session: SessionState) -> SessionState:
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def all(self) -> list[SessionState]:
        with self._lock:
            return list(self._sessions.values())

    def reset(self) -> None:
        with self._lock:
            self._sessions = {}


session_store = SessionStore()
