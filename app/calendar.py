"""Read-only calendar projection. Dates retain the existing event time semantics."""
from datetime import date, timedelta

from .monitor import BJ, dt, utcnow, views


def event_day(event):
    value = event["time"]
    return value if len(value) == 10 else dt(value).astimezone(BJ).date().isoformat()


def calendar_view(store, month=None, day=None, offset=0, limit=20, now=None):
    now = now or utcnow()
    status, events = views(store, now)
    dated = [(event_day(event), event) for event in events]
    latest = dated[0][0] if dated else None
    selected = date.fromisoformat(day) if day else None
    month = month or (day or latest or now.astimezone(BJ).date().isoformat())[:7]
    first = date.fromisoformat(month + "-01")
    if not 1900 <= first.year <= 9998:
        raise ValueError("month out of range")
    if selected and selected.strftime("%Y-%m") != month:
        raise ValueError("day must belong to month")
    month_events = [(key, event) for key, event in dated if key.startswith(month)]
    today = now.astimezone(BJ).date().isoformat()
    fallback = today if today.startswith(month) else first.isoformat()
    selected = selected or date.fromisoformat(month_events[0][0] if month_events else fallback)
    start = first - timedelta(days=first.weekday())
    days = {}
    for number in range(42):
        key = (start + timedelta(days=number)).isoformat()
        days[key] = {"date": key, "direct_reset": 0, "reset_credit": 0, "announced": 0, "total": 0}
    for key, event in dated:
        if key in days:
            days[key]["total"] += 1
            days[key]["announced" if event["status"] == "announced" else event["type"]] += 1
    selected_items = [event for key, event in dated if key == selected.isoformat()]
    totals = {"direct_reset": 0, "reset_credit": 0, "announced": 0, "total": len(month_events)}
    for _, event in month_events:
        totals["announced" if event["status"] == "announced" else event["type"]] += 1
    return {"status": status, "month": month, "selected_date": selected.isoformat(),
            "today": today, "latest_date": latest,
            "days": list(days.values()), "totals": totals,
            "items": selected_items[offset:offset + limit], "total": len(selected_items),
            "offset": offset, "limit": limit}
