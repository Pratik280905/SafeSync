from __future__ import annotations

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt


def due_at(incident: dict, clause: dict) -> str:
    base = incident["occurred_at"] if clause["clock_starts"] == "occurrence" else incident["reported_at"]
    return (parse_dt(base) + timedelta(hours=int(clause["window_hours"]))).isoformat()


def clock_state(due_at_iso: str, now: datetime | None = None) -> tuple[str, float]:
    now = now or datetime.now(IST)
    remaining = (parse_dt(due_at_iso) - now).total_seconds() / 3600
    if remaining < 0:
        return "missed", remaining
    if remaining < 4:
        return "critical", remaining
    if remaining < 12:
        return "warning", remaining
    return "ok", remaining
