import json
import sqlite3
import threading
import time
import tempfile
import os
from pathlib import Path
from .contracts import Lesson, Source
from .errors import AppError

class Store:
    def __init__(self, data):
        self.data = data
        self.lock = threading.RLock()
        self.db = sqlite3.connect(data / "records.sqlite3", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lessons (id TEXT PRIMARY KEY, request_id TEXT UNIQUE, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (lesson_id TEXT, seq INTEGER, body TEXT, PRIMARY KEY(lesson_id, seq));
        CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, body TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, lesson_id TEXT, short_id TEXT, kind TEXT);
        """)
        self.db.commit()

    def put_source(self, source: Source):
        path = self.data / "transcripts" / f"{source.id}.json"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=source.id, suffix=".tmp", delete=False) as file:
            file.write(source.model_dump_json())
            file.flush()
            os.fsync(file.fileno())
            temp = self.data / "transcripts" / Path(file.name).name
        temp.replace(path)
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO sources VALUES (?,?)", (source.id, source.model_dump_json()))
        return source

    def sources(self):
        with self.lock:
            return [Source.model_validate_json(r[0]) for r in self.db.execute("SELECT body FROM sources ORDER BY rowid DESC")]

    def source(self, sid):
        with self.lock:
            row = self.db.execute("SELECT body FROM sources WHERE id=?", (sid,)).fetchone()
        if not row:
            raise AppError("SOURCE_NOT_FOUND", "The source is missing. Import it again.", 404)
        return Source.model_validate_json(row[0])

    def save(self, lesson: Lesson, *, resume=False):
        with self.lock, self.db:
            row = self.db.execute("SELECT body FROM lessons WHERE id=?", (lesson.id,)).fetchone()
            current = Lesson.model_validate_json(row[0]) if row else None
            if current and current.job.status == "cancelled" and not resume and lesson.job.status != "cancelled":
                # Cancellation can race a provider result. Keep spend/reservations,
                # but do not publish new media or overwrite the user's decision.
                ready_ids = {s.id for s in current.shorts if s.status == "ready"}
                lesson.status = "cancelled"
                lesson.job.status = "cancelled"
                lesson.job.stage = "cancelled"
                for short in lesson.shorts:
                    if short.id not in ready_ids:
                        short.status = "cancelled"
                from .planning import refresh
                refresh(lesson)
            lesson.job.updated_at = time.time()
            lesson.job.event_sequence = max(lesson.job.event_sequence, current.job.event_sequence if current else 0) + 1
            body = lesson.model_dump_json()
            self.db.execute("INSERT INTO lessons VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (lesson.id, lesson.request.request_id, body))
            self.db.execute("INSERT INTO events VALUES (?,?,?)", (lesson.id, lesson.job.event_sequence, json.dumps({"sequence": lesson.job.event_sequence, "stage": lesson.job.stage, "status": lesson.status})))
        return lesson

    def lesson(self, lid):
        with self.lock:
            row = self.db.execute("SELECT body FROM lessons WHERE id=?", (lid,)).fetchone()
        if not row:
            raise AppError("LESSON_NOT_FOUND", "The lesson is missing. Start a new lesson.", 404)
        return Lesson.model_validate_json(row[0])

    def by_request(self, rid):
        with self.lock:
            row = self.db.execute("SELECT id FROM lessons WHERE request_id=?", (rid,)).fetchone()
        return self.lesson(row[0]) if row else None

    def history(self):
        with self.lock:
            return [Lesson.model_validate_json(r[0]) for r in self.db.execute("SELECT body FROM lessons ORDER BY rowid DESC LIMIT 30")]

    def recover(self):
        from .contracts import ErrorInfo
        for lesson in self.history_all():
            if lesson.job.status in {"queued", "running"}:
                lesson.status = "interrupted"
                lesson.job.status = "interrupted"
                lesson.job.stage = "interrupted"
                lesson.job.error = ErrorInfo(code="JOB_INTERRUPTED", message="The server stopped during this lesson. Retry to keep the ready shorts and continue.")
                for short in lesson.shorts:
                    if short.status != "ready":
                        short.status = "failed"
                self.save(lesson)

    def history_all(self):
        with self.lock:
            rows = self.db.execute("SELECT body FROM lessons").fetchall()
        return [Lesson.model_validate_json(r[0]) for r in rows]

    def cache_get(self, key, max_age=None):
        with self.lock:
            row = self.db.execute("SELECT body,created FROM cache WHERE key=?", (key,)).fetchone()
        if not row or (max_age and time.time() - row[1] > max_age):
            return None
        return json.loads(row[0])

    def cache_put(self, key, body):
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)", (key, json.dumps(body), time.time()))

    def events(self, lid, after):
        with self.lock:
            return [(r[0], json.loads(r[1])) for r in self.db.execute("SELECT seq,body FROM events WHERE lesson_id=? AND seq>? ORDER BY seq LIMIT 100", (lid, after))]

    def close(self):
        self.db.close()
