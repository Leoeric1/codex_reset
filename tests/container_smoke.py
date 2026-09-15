"""Run inside the built image with networking disabled; never poll AIHOT."""
import os
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.main import create_app


assert os.getuid() == 10001, "Image must run as the monitor user"
with TemporaryDirectory() as directory:
    with TestClient(create_app(db_path=f"{directory}/smoke.db", start_worker=False)) as client:
        assert client.get("/live").status_code == 200
        assert client.get("/").status_code == 200
        assert client.get("/static/logo.webp").status_code == 200
        latest = client.get("/api/notifications/latest")
        assert latest.status_code == 200
        assert latest.json()["initialized"] is False
        assert latest.json()["items"] == []
        assert client.get("/api/notifications/changes?after=0").status_code == 200
        calendar = client.get("/api/calendar?month=2026-09&day=2026-09-12")
        assert calendar.status_code == 200
        assert len(calendar.json()["days"]) == 42
        assert calendar.json()["items"] == []
    # Exercise the persistent schema reopening path as well.
    with TestClient(create_app(db_path=f"{directory}/smoke.db", start_worker=False)) as client:
        assert client.get("/api/notifications/latest").json()["epoch"] == latest.json()["epoch"]
print("Container smoke passed: non-root, UI, notification API, SQLite reopen; no network")
