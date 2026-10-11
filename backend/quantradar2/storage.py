"""SQLite application metadata; no market-data or legacy database dependency."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED"}
TRANSITIONS = {"QUEUED": {"RUNNING", "CANCELLED"}, "RUNNING": TERMINAL}

def now():
    return datetime.now(timezone.utc).isoformat()

def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)

class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise ValueError("Database schema is newer than this application")
            if version == 0:
                db.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS strategies (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS revisions (
                    id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL REFERENCES strategies(id),
                    revision INTEGER NOT NULL, source TEXT NOT NULL, source_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL, UNIQUE(strategy_id, revision));
                CREATE TRIGGER IF NOT EXISTS immutable_revision_update BEFORE UPDATE ON revisions
                    BEGIN SELECT RAISE(ABORT, 'strategy revisions are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_revision_delete BEFORE DELETE ON revisions
                    BEGIN SELECT RAISE(ABORT, 'strategy revisions are immutable'); END;
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, revision_id TEXT NOT NULL REFERENCES revisions(id),
                    request_json TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN
                        ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED','INTERRUPTED')),
                    created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                    pid INTEGER, process_created REAL, exit_code INTEGER, error TEXT,
                    effective_json TEXT, environment_json TEXT);
                CREATE TRIGGER IF NOT EXISTS immutable_run_input BEFORE UPDATE OF revision_id, request_json ON runs
                    BEGIN SELECT RAISE(ABORT, 'run inputs are immutable'); END;
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id TEXT NOT NULL REFERENCES runs(id), name TEXT NOT NULL,
                    sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, PRIMARY KEY(run_id,name));
                CREATE INDEX IF NOT EXISTS run_status ON runs(status,created_at);
                PRAGMA user_version=2;
                COMMIT;
                """)
            elif version == 1:
                db.executescript("BEGIN IMMEDIATE; ALTER TABLE strategies ADD COLUMN archived INTEGER NOT NULL DEFAULT 0; PRAGMA user_version=2; COMMIT;")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def save_strategy(self, name: str, source: str, strategy_id: str | None = None):
        if not name.strip():
            raise ValueError("Strategy name must not be blank")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if strategy_id:
                if not db.execute("SELECT 1 FROM strategies WHERE id=?", (strategy_id,)).fetchone():
                    raise KeyError(strategy_id)
                db.execute("UPDATE strategies SET name=?,updated_at=? WHERE id=?", (name,now(),strategy_id))
            else:
                strategy_id = uuid.uuid4().hex
                timestamp=now()
                db.execute("INSERT INTO strategies(id,name,created_at,updated_at) VALUES (?,?,?,?)",(strategy_id,name,timestamp,timestamp))
            number=db.execute("SELECT coalesce(max(revision),0)+1 FROM revisions WHERE strategy_id=?",(strategy_id,)).fetchone()[0]
            revision_id=uuid.uuid4().hex
            db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?)",(revision_id,strategy_id,number,source,hashlib.sha256(source.encode()).hexdigest(),now()))
        return self.strategy(strategy_id)

    def strategy(self, strategy_id):
        with self.connection() as db:
            row=db.execute("""SELECT s.*, r.id revision_id,r.revision,r.source,r.source_hash,
                (SELECT count(*) FROM runs x JOIN revisions v ON x.revision_id=v.id WHERE v.strategy_id=s.id) run_count
                FROM strategies s JOIN revisions r ON r.strategy_id=s.id
                WHERE s.id=? ORDER BY r.revision DESC LIMIT 1""",(strategy_id,)).fetchone()
            if not row: raise KeyError(strategy_id)
            return dict(row)

    def strategies(self,include_archived=False):
        with self.connection() as db:
            ids=[r[0] for r in db.execute("SELECT id FROM strategies WHERE archived=0 OR ? ORDER BY updated_at DESC",(int(include_archived),))]
        return [self.strategy(i) for i in ids]

    def archive_strategy(self,strategy_id,archived=True):
        self.strategy(strategy_id)
        with self.connection() as db:
            db.execute("UPDATE strategies SET archived=?,updated_at=? WHERE id=?",(int(archived),now(),strategy_id))
        return self.strategy(strategy_id)

    def revision(self, revision_id):
        with self.connection() as db:
            row=db.execute("SELECT * FROM revisions WHERE id=?",(revision_id,)).fetchone()
            if not row: raise KeyError(revision_id)
            return dict(row)

    def create_run(self, revision_id, request):
        run_id=uuid.uuid4().hex
        with self.connection() as db:
            db.execute("INSERT INTO runs(id,revision_id,request_json,status,created_at) VALUES (?,?,?,'QUEUED',?)",
                (run_id,revision_id,encode(request),now()))
        return self.run(run_id)

    @staticmethod
    def _run(row):
        result=dict(row)
        for field in ("request","effective","environment"):
            raw=result.pop(field+"_json")
            result[field]=json.loads(raw) if raw else None
        return result

    def run(self, run_id):
        with self.connection() as db:
            row=db.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
            if not row:raise KeyError(run_id)
            return self._run(row)

    def runs(self, limit=100, strategy_id=None):
        with self.connection() as db:
            if strategy_id:
                return [self._run(row) for row in db.execute("SELECT x.* FROM runs x JOIN revisions v ON x.revision_id=v.id WHERE v.strategy_id=? ORDER BY x.created_at DESC LIMIT ?",(strategy_id,limit))]
            return [self._run(row) for row in db.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",(limit,))]

    def active_runs(self):
        with self.connection() as db:
            return [self._run(row) for row in db.execute("SELECT * FROM runs WHERE status='RUNNING'")]

    def claim_next(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM runs WHERE status='RUNNING'").fetchone():return None
            row=db.execute("SELECT id FROM runs WHERE status='QUEUED' ORDER BY created_at,rowid LIMIT 1").fetchone()
            if not row:return None
            db.execute("UPDATE runs SET status='RUNNING',started_at=? WHERE id=?",(now(),row[0]))
            run_id=row[0]
        return self.run(run_id)

    def transition(self, run_id, status, **fields):
        allowed={"pid","process_created","exit_code","error","effective_json","environment_json"}
        if set(fields)-allowed:raise ValueError("Unknown run metadata")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT status FROM runs WHERE id=?",(run_id,)).fetchone()
            if not row:raise KeyError(run_id)
            current=row[0]
            if status!=current and status not in TRANSITIONS.get(current,set()):
                raise ValueError(f"Invalid run transition {current} -> {status}")
            if current in TERMINAL:raise ValueError("Terminal run cannot be changed")
            fields["status"]=status
            if status in TERMINAL:fields["finished_at"]=now()
            assignments=",".join(key+"=?" for key in fields)
            db.execute("UPDATE runs SET "+assignments+" WHERE id=?",(*fields.values(),run_id))
        return self.run(run_id)

    def register_artifacts(self, run_id, artifacts):
        with self.connection() as db:
            for item in artifacts:
                db.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?)",
                    (run_id,item["name"],item["sha256"],item["bytes"]))

    def artifacts(self,run_id):
        self.run(run_id)
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT name,sha256,bytes FROM artifacts WHERE run_id=? ORDER BY name",(run_id,))]
