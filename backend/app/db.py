"""MVP 영속 저장: 요청마다 연결, 소유 세션별 접근, 분석 결과와 원본 입력 보관."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import secrets
import sqlite3
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    def __init__(self, path):
        self.path = str(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS objects (id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES sessions(id), kind TEXT NOT NULL, parent TEXT REFERENCES objects(id) ON DELETE CASCADE, payload TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS objects_owner ON objects(owner,kind);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def session(self):
        token, sid = secrets.token_urlsafe(32), str(uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (sid, digest(token), now()))
        return token

    def owner(self, token):
        with self.connect() as db:
            row = db.execute("SELECT id FROM sessions WHERE token_hash=?", (digest(token),)).fetchone()
        return row['id'] if row else None

    def create(self, owner, kind, payload, parent=None):
        oid, date = str(uuid4()), now()
        with self.connect() as db:
            db.execute("INSERT INTO objects VALUES(?,?,?,?,?,?)", (oid,owner,kind,parent,json.dumps(payload,ensure_ascii=False,allow_nan=False),date))
        return dict(id=oid,created_at=date,**payload)

    def get(self, oid, owner, kind):
        with self.connect() as db:
            row = db.execute("SELECT * FROM objects WHERE id=? AND owner=? AND kind=?",(oid,owner,kind)).fetchone()
        return dict(id=row['id'],created_at=row['created_at'],**json.loads(row['payload'])) if row else None

    def delete(self, oid, owner, kind):
        with self.connect() as db:
            return db.execute("DELETE FROM objects WHERE id=? AND owner=? AND kind=?", (oid,owner,kind)).rowcount > 0

    def delete_session(self, owner):
        with self.connect() as db:
            db.execute("DELETE FROM objects WHERE owner=?", (owner,))
            db.execute("DELETE FROM sessions WHERE id=?", (owner,))
