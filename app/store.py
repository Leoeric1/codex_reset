import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
                    status TEXT NOT NULL, first_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, raw_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sync_state (
                    id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL
                );
                INSERT OR IGNORE INTO sync_state VALUES (1, '{}');
                CREATE TABLE IF NOT EXISTS notifications (
                    event_id TEXT NOT NULL, notification_type TEXT NOT NULL,
                    disposition TEXT NOT NULL, created_at TEXT NOT NULL,
                    sent_at TEXT, PRIMARY KEY(event_id, notification_type)
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def read(self):
        with self.connection() as db:
            # Read state and events from a single consistent transaction.
            db.execute("BEGIN")
            state = json.loads(db.execute("SELECT data FROM sync_state WHERE id=1").fetchone()[0])
            events = [json.loads(r[0]) for r in db.execute("SELECT raw_json FROM events")]
        return state, events

    def update_state(self, state):
        with self.connection() as db:
            db.execute("UPDATE sync_state SET data=? WHERE id=1", (json.dumps(state),))

    def sync(self, snapshot, state, now):
        incoming = {e.id: e.model_dump(mode="json", by_alias=True) for e in snapshot.events}
        with self.connection() as db:
            old = {r[0]: json.loads(r[1]) for r in db.execute("SELECT event_id,raw_json FROM events")}
            first = not json.loads(db.execute("SELECT data FROM sync_state WHERE id=1").fetchone()[0]).get("has_snapshot")
            diff = {"added": len(incoming.keys() - old.keys()), "removed": len(old.keys() - incoming.keys()),
                    "modified": sum(old[k] != incoming[k] for k in old.keys() & incoming.keys())}
            for key in old.keys() - incoming.keys():
                # A withdrawn event must disappear, including its cached original text.
                db.execute("DELETE FROM events WHERE event_id=?", (key,))
                db.execute("UPDATE notifications SET disposition='cancelled' WHERE event_id=? AND sent_at IS NULL", (key,))
            for key, e in incoming.items():
                raw = json.dumps(e, ensure_ascii=False, sort_keys=True)
                db.execute("""INSERT INTO events VALUES (?,?,?,?,?,?)
                    ON CONFLICT(event_id) DO UPDATE SET event_type=excluded.event_type,
                    status=excluded.status,updated_at=excluded.updated_at,raw_json=excluded.raw_json""",
                    (key, e["type"], e["status"], now, e["updatedAt"], raw))
                kind = ("reset_announcement" if e["status"] == "announced" else "reset_confirmed") if e["type"] == "direct_reset" else "reset_credit_" + e["status"]
                # Reserved notification hook only. V1 has no sender and never claims delivery.
                if key not in old or old[key]["status"] != e["status"] or old[key]["type"] != e["type"]:
                    db.execute("UPDATE notifications SET disposition='cancelled' WHERE event_id=? AND disposition='disabled'", (key,))
                    db.execute("INSERT OR IGNORE INTO notifications VALUES (?,?,?,?,NULL)",
                               (key, kind, "initial_suppressed" if first else "disabled", now))
            state.update(has_snapshot=True, last_diff=diff)
            db.execute("UPDATE sync_state SET data=? WHERE id=1", (json.dumps(state),))
        return diff
