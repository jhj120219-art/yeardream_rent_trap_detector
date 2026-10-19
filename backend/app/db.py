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


class InvalidReference(ValueError):
    pass


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
            CREATE TABLE IF NOT EXISTS object_links (
                object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
                relation TEXT NOT NULL CHECK(relation IN ('source_extraction_id','previous_listing_id')),
                target_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
                PRIMARY KEY(object_id,relation)
            );
            CREATE INDEX IF NOT EXISTS object_links_target ON object_links(target_id);
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

    def create(self, owner, kind, payload, parent=None, links=None):
        oid, date = str(uuid4()), now()
        with self.connect() as db:
            for relation, target in (links or {}).items():
                target_kind = {'source_extraction_id':'extraction','previous_listing_id':'listing'}.get(relation)
                found = db.execute('SELECT id FROM objects WHERE id=? AND owner=? AND kind=?',
                                   (target, owner, target_kind)).fetchone()
                if not found or kind != 'listing':
                    raise InvalidReference('자료를 찾을 수 없습니다.')
            db.execute("INSERT INTO objects VALUES(?,?,?,?,?,?)", (oid,owner,kind,parent,json.dumps(payload,ensure_ascii=False,allow_nan=False),date))
            for relation, target in (links or {}).items():
                db.execute('INSERT INTO object_links VALUES(?,?,?)', (oid, relation, target))
        return self.get(oid, owner, kind)

    def public_object(self, db, row):
        obj = dict(id=row['id'],created_at=row['created_at'],**json.loads(row['payload']))
        if row['kind'] == 'listing':
            links = {r['relation']:r['target_id'] for r in db.execute(
                'SELECT relation,target_id FROM object_links WHERE object_id=?', (row['id'],))}
            obj['links'] = {name:links.get(name) for name in ('source_extraction_id','previous_listing_id')}
        return obj

    def get(self, oid, owner, kind):
        with self.connect() as db:
            row = db.execute("SELECT * FROM objects WHERE id=? AND owner=? AND kind=?",(oid,owner,kind)).fetchone()
            return self.public_object(db, row) if row else None

    def page(self, owner, kind, limit, offset):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM objects WHERE owner=? AND kind=? ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?',
                              (owner,kind,limit+1,offset)).fetchall()
            return {'items':[self.public_object(db,row) for row in rows[:limit]],
                    'limit':limit, 'offset':offset, 'has_more':len(rows)>limit}

    def children(self, parent, owner, kind, limit=20, offset=0):
        with self.connect() as db:
            total=db.execute('SELECT COUNT(*) FROM objects WHERE parent=? AND owner=? AND kind=?',
                             (parent,owner,kind)).fetchone()[0]
            rows = db.execute('SELECT * FROM objects WHERE parent=? AND owner=? AND kind=? ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?',
                              (parent,owner,kind,limit+1,offset)).fetchall()
            return {'items':[self.public_object(db,row) for row in rows[:limit]],
                    'limit':limit,'offset':offset,'has_more':len(rows)>limit,'total':total}

    def delete(self, oid, owner, kind):
        with self.connect() as db:
            return db.execute("DELETE FROM objects WHERE id=? AND owner=? AND kind=?", (oid,owner,kind)).rowcount > 0

    def delete_session(self, owner):
        with self.connect() as db:
            db.execute("DELETE FROM objects WHERE owner=?", (owner,))
            db.execute("DELETE FROM sessions WHERE id=?", (owner,))
