import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .models import RunRequest


def now() -> str:
    return datetime.now(UTC).isoformat()


class IdempotencyConflict(ValueError):
    pass


class JobStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE, fingerprint TEXT NOT NULL,
                request_json TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                result_json TEXT, error TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES jobs(id), time TEXT NOT NULL,
                event TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_run ON events(run_id, sequence);
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def find_key(self, key: str | None, fingerprint: str):
        if key is None:
            return None
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE idempotency_key=?", (key,)
            ).fetchone()
        if row and row["fingerprint"] != fingerprint:
            raise IdempotencyConflict("idempotency key was already used for a different request")
        return self.decode(row) if row else None

    def create(self, request: RunRequest, key: str | None, fingerprint: str):
        existing = self.find_key(key, fingerprint)
        if existing:
            return existing, False
        run_id = uuid.uuid4().hex
        try:
            with self.connect() as connection:
                connection.execute(
                    "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        key,
                        fingerprint,
                        request.model_dump_json(),
                        "queued",
                        now(),
                        now(),
                        None,
                        None,
                    ),
                )
                self.append_event(connection, run_id, "job.queued", {})
        except sqlite3.IntegrityError:
            return self.find_key(key, fingerprint), False
        return self.get(run_id), True

    def get(self, run_id: str):
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (run_id,)).fetchone()
        return self.decode(row) if row else None

    @staticmethod
    def decode(row):
        item = dict(row)
        item["request"] = json.loads(item.pop("request_json"))
        result = item.pop("result_json")
        item["result"] = json.loads(result) if result else None
        item.pop("fingerprint")
        item.pop("idempotency_key")
        return item

    def claim(self, run_id: str) -> bool:
        with self.connect() as connection:
            updated = connection.execute(
                "UPDATE jobs SET status='running',updated_at=? WHERE id=? AND status='queued'",
                (now(), run_id),
            ).rowcount
            if updated:
                self.append_event(connection, run_id, "job.running", {})
        return bool(updated)

    def finish(self, run_id: str, result: dict):
        with self.connect() as connection:
            connection.execute(
                "UPDATE jobs SET status='completed',result_json=?,updated_at=? WHERE id=?",
                (json.dumps(result, ensure_ascii=False), now(), run_id),
            )
            self.append_event(connection, run_id, "job.completed", {"decision": result["decision"]})

    def fail(self, run_id: str, message: str):
        with self.connect() as connection:
            connection.execute(
                "UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=?",
                (message, now(), run_id),
            )
            self.append_event(connection, run_id, "job.failed", {"error": message})

    def recover(self) -> int:
        with self.connect() as connection:
            return connection.execute(
                "UPDATE jobs SET status='interrupted',updated_at=? "
                "WHERE status IN ('queued','running')",
                (now(),),
            ).rowcount

    def emit(self, run_id: str, event: str, **payload):
        with self.connect() as connection:
            self.append_event(connection, run_id, event, payload)

    @staticmethod
    def append_event(connection, run_id: str, event: str, payload: dict):
        connection.execute(
            "INSERT INTO events(run_id,time,event,payload_json) VALUES (?,?,?,?)",
            (run_id, now(), event, json.dumps(payload, ensure_ascii=False)),
        )

    def events(self, run_id: str):
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT sequence,time,event,payload_json FROM events "
                "WHERE run_id=? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        return [
            dict(
                sequence=row["sequence"],
                time=row["time"],
                event=row["event"],
                payload=json.loads(row["payload_json"]),
            )
            for row in rows
        ]
