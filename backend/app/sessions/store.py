from app.sessions.models import SessionState


class SessionStore:
    """In-memory session store, keyed by session_id. Resets on process restart."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str) -> SessionState:
        session = self._sessions.get(session_id)
        if session is None:
            session = SessionState(session_id=session_id, mem0_user_id=session_id)
            self._sessions[session_id] = session
        return session

    def save(self, session: SessionState) -> SessionState:
        self._sessions[session.session_id] = session
        return session

    def all(self) -> list[SessionState]:
        return list(self._sessions.values())

    def reset(self) -> None:
        self._sessions = {}


session_store = SessionStore()
