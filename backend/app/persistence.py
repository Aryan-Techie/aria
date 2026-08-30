"""Optional JSON snapshotting for the demo stores.

The CRM, calendar and escalation inbox are deliberately in-memory - they are a
stand-in for a real CRM, not one worth wiring up for a hackathon. The problem
is the demo itself: restart the backend between rehearsals (or mid-session)
and the booked meeting and captured lead you just demonstrated vanish, with no
error to explain why.

So when `STATE_DIR` is set, each store snapshots itself to a small JSON file
after every write and reloads it on startup. When it is unset the stores stay
purely in-memory and never touch the filesystem - which is what happens under
pytest, since conftest.py blanks `env_file` and the setting falls back to "".

Writes go to a temp file and are then moved into place, so a crash mid-write
leaves the previous good snapshot rather than a truncated one.
"""
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("aria.persistence")


def _state_dir() -> Path | None:
    from app.config import get_settings

    configured = get_settings().state_dir
    if not configured:
        return None
    path = Path(configured)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("could not create state dir %s; persistence disabled", path, exc_info=True)
        return None
    return path


def load_state(name: str) -> Any | None:
    """Returns the snapshot for `name`, or None if disabled/absent/unreadable."""
    directory = _state_dir()
    if directory is None:
        return None
    target = directory / f"{name}.json"
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("ignoring unreadable snapshot %s", target, exc_info=True)
        return None


def save_state(name: str, data: Any) -> None:
    """Best-effort atomic write. Never raises - a snapshot failure must not
    break a live call."""
    directory = _state_dir()
    if directory is None:
        return
    target = directory / f"{name}.json"
    try:
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=f".{name}.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, default=str)
        os.replace(tmp, target)
    except OSError:
        logger.warning("could not write snapshot %s", target, exc_info=True)
