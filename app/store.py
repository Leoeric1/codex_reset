import json
import sqlite3
import uuid
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
                CREATE TABLE IF NOT EXISTS hub_events (
                    event_id TEXT NOT NULL, kind TEXT NOT NULL, active INTEGER NOT NULL,
                    created_at TEXT NOT NULL, PRIMARY KEY(event_id, kind)
                );
                CREATE TABLE IF NOT EXISTS notification_changes (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
                    kind TEXT NOT NULL, operation TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notification_stream (
                    id INTEGER PRIMARY KEY CHECK(id=1), epoch TEXT NOT NULL
                );
            """)
            db.execute("INSERT OR IGNORE INTO notification_stream VALUES (1,?)", (uuid.uuid4().hex,))

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
                self._cancel_hub(db, key)
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
                    self._cancel_hub(db, key)
                    db.execute("UPDATE notifications SET disposition='cancelled' WHERE event_id=? AND disposition='disabled'", (key,))
                    inserted = db.execute("INSERT OR IGNORE INTO notifications VALUES (?,?,?,?,NULL)",
                               (key, kind, "initial_suppressed" if first else "disabled", now))
                    if inserted.rowcount and not first:
                        db.execute("INSERT INTO hub_events VALUES (?,?,1,?)", (key, kind, now))
                        self._change(db, key, kind, 'upsert')
                elif old[key] != e:
                    # Text revisions refresh an existing alert without resetting its read state.
                    if db.execute("SELECT 1 FROM hub_events WHERE event_id=? AND kind=? AND active=1", (key, kind)).fetchone():
                        self._change(db, key, kind, 'upsert')
            state.update(has_snapshot=True, last_diff=diff)
            db.execute("UPDATE sync_state SET data=? WHERE id=1", (json.dumps(state),))
        return diff

    @staticmethod
    def _change(db, key, kind, operation):
        db.execute("INSERT INTO notification_changes(event_id,kind,operation) VALUES (?,?,?)", (key, kind, operation))

    def _cancel_hub(self, db, key):
        for row in db.execute("SELECT kind FROM hub_events WHERE event_id=? AND active=1", (key,)).fetchall():
            self._change(db, key, row['kind'], 'cancel')
        db.execute("UPDATE hub_events SET active=0 WHERE event_id=?", (key,))

    def notification_feed(self, now, after=None, limit=10):
        from .notifications import project, notification_id
        from .monitor import dt
        with self.connection() as db:
            db.execute("BEGIN")
            state = json.loads(db.execute("SELECT data FROM sync_state WHERE id=1").fetchone()[0])
            epoch = db.execute("SELECT epoch FROM notification_stream WHERE id=1").fetchone()[0]
            cursor = db.execute("SELECT COALESCE(MAX(seq),0) FROM notification_changes").fetchone()[0]
            base = {'schema_version': 1, 'initialized': bool(state.get('has_snapshot')),
                    'epoch': epoch, 'cursor': cursor, 'updated_at': state.get('last_snapshot_at')}
            if after is not None and after > cursor:
                raise ValueError('cursor_ahead')
            def item(row):
                raw = db.execute("SELECT raw_json FROM events WHERE event_id=?", (row['event_id'],)).fetchone()
                h = db.execute("SELECT * FROM hub_events WHERE event_id=? AND kind=?", (row['event_id'], row['kind'])).fetchone()
                if not raw or not h or not h['active']:
                    return None
                return project(json.loads(raw[0]), row['kind'], h['created_at'], now)
            if after is None:
                rows = db.execute("SELECT * FROM hub_events WHERE active=1 ORDER BY created_at DESC,event_id DESC,kind LIMIT ?", (limit,)).fetchall()
                items = [p for r in rows if (p := item(r)) and (not p['expires_at'] or dt(p['expires_at']) >= now)]
                return dict(base, items=items)
            rows = db.execute("SELECT * FROM notification_changes WHERE seq>? ORDER BY seq LIMIT ?", (after, limit)).fetchall()
            items = []
            for row in rows:
                p = item(row) if row['operation'] == 'upsert' else None
                items.append({'seq': row['seq'], 'operation': 'upsert' if p else 'cancel',
                              'notification_id': notification_id(row['event_id'], row['kind']), 'item': p})
            next_cursor = rows[-1]['seq'] if rows else after
            return dict(base, items=items, next_cursor=next_cursor, has_more=next_cursor < cursor)
