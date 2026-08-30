from datetime import datetime, timedelta, timezone

from app.calendar.models import Slot

REPS = ["Dana Kwon", "Sam Osei", "Rahul Mehta"]
HOURS = [10, 14, 16]  # fixed local-time hours each open day


def seed_slots(days_ahead: int = 5, start_from: datetime | None = None) -> list[Slot]:
    """Generate open slots for the next `days_ahead` business days."""
    base = (start_from or datetime.now(timezone.utc)).replace(
        minute=0, second=0, microsecond=0
    )
    slots: list[Slot] = []
    day_offset = 1
    business_days_added = 0
    rep_cycle = 0

    while business_days_added < days_ahead:
        day = base + timedelta(days=day_offset)
        day_offset += 1
        if day.weekday() >= 5:  # skip Sat/Sun
            continue
        for hour in HOURS:
            start = day.replace(hour=hour)
            slots.append(
                Slot(
                    start=start,
                    end=start + timedelta(minutes=30),
                    rep_name=REPS[rep_cycle % len(REPS)],
                )
            )
            rep_cycle += 1
        business_days_added += 1

    return slots
