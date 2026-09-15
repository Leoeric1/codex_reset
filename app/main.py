import asyncio
import fcntl
import logging
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .monitor import Monitor, views, utcnow
from .store import Store

STATIC = Path(__file__).parent / "static"


def create_app(db_path=None, start_worker=True):
    db_path = db_path or os.environ.get("DB_PATH", "/data/codex-reset.db")

    @asynccontextmanager
    async def lifespan(app):
        from .notifications import create_sender
        app.state.notification_sender = create_sender()
        store = Store(db_path)
        app.state.store = store
        lock, task = None, None
        try:
            if start_worker:
                lock = open(str(db_path) + ".worker.lock", "a")
                # Fail closed if someone starts multiple Uvicorn workers/containers on this volume.
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                task = asyncio.create_task(Monitor(store).run(), name="aihot-poller")
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if lock:
                lock.close()

    app = FastAPI(title="Codex Reset Monitor", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    def status():
        return views(app.state.store)[0]

    @app.get("/api/events/latest")
    def latest():
        s = views(app.state.store)[0]
        return {key: s[key] for key in ("latest_reset", "latest_credit", "announcements")}

    @app.get("/api/events")
    def events(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
               type: Literal["direct_reset", "reset_credit"] | None = None,
               status: Literal["announced", "confirmed"] | None = None):
        _, rows = views(app.state.store)
        rows = [e for e in rows if (not type or e["type"] == type) and (not status or e["status"] == status)]
        return {"total": len(rows), "items": rows[offset:offset + limit], "offset": offset, "limit": limit}

    @app.get("/api/notifications/latest")
    def notifications_latest(limit: int = Query(10, ge=1, le=10)):
        return app.state.store.notification_feed(utcnow(), limit=limit)

    @app.get("/api/notifications/changes")
    def notifications_changes(after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100)):
        try:
            return app.state.store.notification_feed(utcnow(), after=after, limit=limit)
        except ValueError:
            return JSONResponse({'code': 'cursor_ahead'}, status_code=409)

    @app.get("/health")
    def health():
        try:
            s = views(app.state.store)[0]
            body = {k: s[k] for k in ("status", "source", "last_sync", "checked_at", "data_age_seconds", "consecutive_failures")}
            return JSONResponse(body, status_code=200 if s["status"] == "ok" else 503)
        except Exception:
            return JSONResponse({"status": "error", "source": "unknown"}, status_code=503)

    @app.get("/live")
    def live():
        return {"status": "ok"}

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
app = create_app()
