"""One human-readable rendering of a slot time, shared by the tool layer and
the confirmation email.

It lives here rather than in tools/executor.py because notify/service.py needs
the identical string - the customer hears "Tuesday 1 September at 10:00 AM" on
the call and must read exactly that in their inbox. Two formatters drift.
"""
from __future__ import annotations

import os
from datetime import datetime


def slot_label(start: datetime) -> str:
    """"Tuesday 1 September at 10:00 AM".

    glibc and MSVC disagree on the no-padding strftime flag - "%-d" on Linux,
    "%#d" on Windows - and the wrong one is not an error, it emits the literal
    text. Branch on the platform rather than shipping "Tuesday %-d September".
    """
    fmt = "%A %#d %B at %#I:%M %p" if os.name == "nt" else "%A %-d %B at %-I:%M %p"
    return start.strftime(fmt)
