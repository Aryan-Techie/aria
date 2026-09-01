import pytest

# Module-level, not inside a fixture: this must run before any test module is
# imported, because app/main.py calls get_settings() at IMPORT time (not just
# call time), and conftest.py is guaranteed to load before sibling test files.
# A fixture would run too late to catch that.
#
# Found live, not by inspection: without this, Settings() reads the project's
# real backend/.env, and a test hitting /api/call/start made an actual call to
# Agora's REST API with real credentials. No orphaned agent was left behind
# (checked via list_agents), but the test suite must never depend on what's in
# the developer's real .env — it stays hermetic regardless of local secrets.
from app.config import Settings, get_settings  # noqa: E402

Settings.model_config["env_file"] = None
get_settings.cache_clear()

from app.calendar.store import calendar_store  # noqa: E402
from app.crm.store import lead_store  # noqa: E402
from app.escalation.inbox import inbox  # noqa: E402
from app.handoff import service as handoff_service  # noqa: E402
from app.sessions.store import session_store  # noqa: E402


@pytest.fixture(autouse=True)
def reset_global_stores():
    """Executor handlers (app/tools/executor.py) call the crm/calendar/escalation
    services using their default module-level singleton stores, so endpoint-level
    tests need those reset between runs to stay deterministic and order-independent."""
    lead_store.reset()
    calendar_store.reset()
    inbox.reset()
    session_store.reset()
    handoff_service.reset()
    yield
