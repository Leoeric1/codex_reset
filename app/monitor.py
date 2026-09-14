import asyncio
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
import httpx
from .models import Snapshot

SOURCE = "https://aihot.news/api/v1/codex-resets"
INTERVAL = 300
STALE_SECONDS = 1800
MAX_BYTES = 4 * 1024 * 1024
BJ = timezone(timedelta(hours=8))
log = logging.getLogger("codex-reset-monitor")


def utcnow():
    return datetime.now(timezone.utc)


def iso(value):
    return value.astimezone(BJ).isoformat(timespec="seconds")


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def age(value, now):
    return max(0, int((now - dt(value)).total_seconds())) if value else None


def retry_delay(value, now):
    if not value:
        return None
    try:
        seconds = float(value)
        return max(INTERVAL, seconds) if math.isfinite(seconds) else None
    except ValueError:
        try:
            return max(INTERVAL, (parsedate_to_datetime(value) - now).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


def safe_url(value):
    try:
        url = urlsplit(value or "")
        if url.scheme == "https" and url.hostname in {"x.com", "twitter.com", "aihot.news"} and not url.username and not url.password:
            return value
    except ValueError:
        pass
    return None


def present(e, now):
    schedule = e.get("schedule")
    end = schedule and (schedule.get("through") or schedule.get("from"))
    # No unsupported prediction: old unconfirmed announcements remain in history only.
    expired = e["status"] == "announced" and (
        (bool(end) and dt(end) < now) or (not end and age(e["createdAt"], now) > 86400))
    posts = sorted(e["posts"], key=lambda p: dt(p["publishedAt"]), reverse=True)
    if e.get("confirmedAt"):
        when, precision = e["confirmedAt"], "confirmed"
    elif e.get("occurredOn"):
        when, precision = e["occurredOn"], "date"
    else:
        when, precision = e["createdAt"], "post"
    return {"id": e["id"], "type": e["type"], "status": e["status"], "title": e["title"],
            "scope": e["scope"], "time": when, "time_precision": precision,
            "announced_at": e["createdAt"], "confirmed_at": e.get("confirmedAt"),
            "confirmation_basis": e.get("confirmationBasis"), "schedule": schedule,
            "expired": bool(expired), "source_url": "https://aihot.news/codex-reset",
            "posts": [{"time": p["publishedAt"], "stage": p["stage"], "text": p["text"],
                       "url": safe_url(p["url"])} for p in posts]}


def views(store, now=None):
    now = now or utcnow()
    state, raw = store.read()
    failures = state.get("consecutive_failures", 0)
    transport_age = age(state.get("last_success_at"), now)
    source_age = age(state.get("checked_at"), now)
    stale = source_age is None or source_age > STALE_SECONDS
    local_stale = transport_age is None or transport_age > STALE_SECONDS
    color = "red" if failures >= 6 else "yellow" if failures >= 3 or stale or local_stale else "green"
    source = "unavailable" if failures >= 3 else "stale" if stale else "ok"
    events = [present(e, now) for e in raw]
    def order(e):
        t = e["time"]
        return dt(t + "T00:00:00+08:00" if len(t) == 10 else t)
    events.sort(key=order, reverse=True)
    def latest(kind):
        return next((e for e in events if e["type"] == kind and e["status"] == "confirmed"), None)
    pending = sorted([e for e in events if e["status"] == "announced" and not e["expired"]],
                     key=lambda e: dt(e["announced_at"]), reverse=True)
    status = {"status": "ok" if color == "green" else "degraded", "source": source,
              "color": color, "checked_at": state.get("checked_at"),
              "last_sync": state.get("last_success_at"), "last_snapshot_at": state.get("last_snapshot_at"),
              "next_check_at": state.get("next_check_at"), "data_age_seconds": source_age,
              "connection_age_seconds": transport_age, "consecutive_failures": failures,
              "last_error": state.get("last_error"), "has_data": state.get("has_snapshot", False),
              "timezone": "Asia/Shanghai", "total": len(events),
              "notification_channel": "disabled", "last_diff": state.get("last_diff"),
              "latest_reset": latest("direct_reset"), "latest_credit": latest("reset_credit"),
              "announcements": pending, "source_url": "https://aihot.news/codex-reset"}
    return status, events


class Monitor:
    def __init__(self, store, client=None, clock=utcnow):
        self.store, self.client, self.clock = store, client, clock
        self.lock = asyncio.Lock()

    async def poll(self):
        async with self.lock:
            state, _ = await asyncio.to_thread(self.store.read)
            now = self.clock()
            # Persisted Retry-After/minimum interval survives process restarts.
            if state.get("next_check_at") and dt(state["next_check_at"]) > now:
                return (dt(state["next_check_at"]) - now).total_seconds()
            state.update(last_attempt_at=iso(now), next_check_at=iso(now + timedelta(seconds=INTERVAL)))
            await asyncio.to_thread(self.store.update_state, state)
            headers = {"Accept": "application/json", "User-Agent": "CodexResetMonitor/1.0 (personal-use)"}
            if state.get("etag") and state.get("has_snapshot"):
                headers["If-None-Match"] = state["etag"]
            response = None
            try:
                # Bound the total request duration and decoded response size.
                async with asyncio.timeout(30):
                    async with self.client.stream("GET", SOURCE, headers=headers) as response:
                        if response.status_code == 304:
                            if not state.get("has_snapshot") or not headers.get("If-None-Match"):
                                raise ValueError("unexpected 304 without cached snapshot")
                            body = None
                        else:
                            response.raise_for_status()
                            if response.status_code != 200:
                                raise ValueError("expected HTTP 200 snapshot")
                            chunks, length = [], 0
                            async for chunk in response.aiter_bytes():
                                length += len(chunk)
                                if length > MAX_BYTES:
                                    raise ValueError("snapshot exceeds size limit")
                                chunks.append(chunk)
                            body = b"".join(chunks)
                snapshot = Snapshot.model_validate_json(body) if body is not None else None
                now = self.clock()
                if snapshot and snapshot.checkedAt and snapshot.checkedAt > now + timedelta(minutes=5):
                    raise ValueError("upstream checkedAt is in the future")
                if snapshot and snapshot.checkedAt and state.get("checked_at") and snapshot.checkedAt < dt(state["checked_at"]):
                    raise ValueError("upstream snapshot checkedAt regressed")
                state.update(last_success_at=iso(now), last_error=None, consecutive_failures=0,
                             next_check_at=iso(now + timedelta(seconds=INTERVAL)))
                if snapshot:
                    state.update(etag=response.headers.get("etag"), checked_at=iso(snapshot.checkedAt) if snapshot.checkedAt else None,
                                 last_snapshot_at=iso(now))
                    changes = await asyncio.to_thread(self.store.sync, snapshot, state, iso(now))
                    log.info("snapshot synced added=%s modified=%s removed=%s", *changes.values())
                else:
                    # checkedAt is an upstream fact; a 304 cannot advance it.
                    await asyncio.to_thread(self.store.update_state, state)
                return INTERVAL
            except Exception as exc:
                # Re-read committed state: never persist an ETag for a failed transaction.
                state, _ = await asyncio.to_thread(self.store.read)
                failures = state.get("consecutive_failures", 0) + 1
                delay = min(3600, INTERVAL * 2 ** min(failures - 1, 4))
                if response is not None and response.status_code in (429, 503):
                    delay = retry_delay(response.headers.get("retry-after"), self.clock()) or delay
                code = response.status_code if response is not None else None
                # No source posts, request headers or credentials in error logs.
                error = f"HTTP {code}" if code and code >= 400 else type(exc).__name__
                state.update(consecutive_failures=failures, last_error=error,
                             next_check_at=iso(self.clock() + timedelta(seconds=delay)))
                await asyncio.to_thread(self.store.update_state, state)
                log.warning("source check failed kind=%s failures=%s retry_seconds=%s", error, failures, delay)
                return delay

    async def run(self):
        async with httpx.AsyncClient(timeout=httpx.Timeout(15), follow_redirects=False) as client:
            self.client = client
            while True:
                try:
                    delay = await self.poll()
                except Exception:
                    # Disk failure must not silently terminate the only worker.
                    log.exception("worker persistence failure")
                    delay = INTERVAL
                await asyncio.sleep(max(1, delay))
