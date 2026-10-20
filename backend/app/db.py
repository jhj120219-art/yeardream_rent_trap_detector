"""MVP 영속 저장: 요청마다 연결, 소유 세션별 접근, 분석 결과와 원본 입력 보관."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import secrets
import sqlite3
from uuid import uuid4, uuid5, NAMESPACE_URL
from pathlib import Path
from urllib.parse import urlsplit, unquote, parse_qs
from . import maintenance_storage

MYSQL_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS sessions (id VARCHAR(36) PRIMARY KEY, token_hash VARCHAR(64) UNIQUE NOT NULL, created_at VARCHAR(40) NOT NULL)",
    "CREATE TABLE IF NOT EXISTS objects (id VARCHAR(36) PRIMARY KEY, owner VARCHAR(36) NOT NULL, kind VARCHAR(64) NOT NULL, parent VARCHAR(36), payload LONGTEXT NOT NULL, created_at VARCHAR(40) NOT NULL, INDEX objects_owner(owner,kind), FOREIGN KEY(owner) REFERENCES sessions(id), FOREIGN KEY(parent) REFERENCES objects(id) ON DELETE CASCADE)",
    "CREATE TABLE IF NOT EXISTS object_links (object_id VARCHAR(36) NOT NULL, relation VARCHAR(32) NOT NULL, target_id VARCHAR(36) NOT NULL, PRIMARY KEY(object_id,relation), INDEX object_links_target(target_id), FOREIGN KEY(object_id) REFERENCES objects(id) ON DELETE CASCADE, FOREIGN KEY(target_id) REFERENCES objects(id) ON DELETE CASCADE, CHECK(relation IN ('source_extraction_id','previous_listing_id')))",
)

MYSQL_SCHEMA += maintenance_storage.MYSQL_SCHEMA


class MySQLConnection:
    """Adapt the existing parameterized Store queries to DB-API cursors."""
    def __init__(self, connection):
        self.connection = connection
        self.cursors = []

    def execute(self, sql, params=()):
        cursor = self.connection.cursor()
        self.cursors.append(cursor)
        cursor.execute(sql.replace('?', '%s'), params)
        return cursor

    def close(self):
        for cursor in self.cursors:
            cursor.close()
        self.connection.close()


def mysql_options(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('mysql', 'mysql+pymysql') or not parsed.hostname or not parsed.username or not parsed.path.strip('/'):
        raise ValueError('DATABASE_URL must be mysql+pymysql://user:password@host:3306/database')
    query = parse_qs(parsed.query)
    if set(query) - {'ssl_ca'}:
        raise ValueError('Unsupported DATABASE_URL option (supported: ssl_ca)')
    options = dict(host=parsed.hostname, port=parsed.port or 3306, user=unquote(parsed.username),
                   password=unquote(parsed.password or ''), database=unquote(parsed.path[1:]),
                   charset='utf8mb4', autocommit=False, connect_timeout=10, read_timeout=30, write_timeout=30)
    if 'ssl_ca' in query:
        options.update(ssl_ca=query['ssl_ca'][0], ssl_verify_cert=True, ssl_verify_identity=True)
    return options


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class InvalidReference(ValueError):
    pass


class RequestConflict(ValueError):
    """A retry key cannot be reused for changed input or a deleted result."""
    pass


class Store:
    def __init__(self, path=None, database_url="", initialize=True):
        self.mysql = bool(database_url)
        if self.mysql:
            self.options = mysql_options(database_url)
            if not initialize:
                return
            with self.connect() as db:
                for statement in MYSQL_SCHEMA:
                    db.execute(statement + " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin")
            return
        if path is None:
            raise ValueError("DATABASE_URL is required; BACKEND_DB_PATH is only for explicit legacy SQLite use")
        path = Path(path)
        self.path = str(path)
        if not initialize:
            return
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
            db.executescript(maintenance_storage.SQLITE_SCHEMA)

    @contextmanager
    def connect(self, timeout=None):
        if self.mysql:
            import pymysql
            options = dict(self.options)
            if timeout is not None:
                options.update(connect_timeout=timeout, read_timeout=timeout, write_timeout=timeout)
            connection = pymysql.connect(**options, cursorclass=pymysql.cursors.DictCursor)
            db = MySQLConnection(connection)
            try:
                yield db
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                db.close()
            return
        db = sqlite3.connect(self.path, timeout=15 if timeout is None else timeout)
        db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def available(self):
        """Readiness probes storage tables using fresh, bounded connections."""
        errors = (sqlite3.Error,)
        if self.mysql:
            import pymysql
            errors += (pymysql.MySQLError,)
        try:
            with self.connect(timeout=2) as db:
                for table, column in (("sessions", "id"), ("objects", "id"), ("object_links", "object_id"),
                                      ("listing_maintenance", "listing_id"), ("listing_maintenance_items", "listing_id")):
                    db.execute(f"SELECT {column} FROM {table} LIMIT 1").fetchone()
            return True
        except errors:
            return False

    def session(self):
        token, sid = secrets.token_urlsafe(32), str(uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (sid, digest(token), now()))
        return token

    def owner(self, token):
        with self.connect() as db:
            row = db.execute("SELECT id FROM sessions WHERE token_hash=?", (digest(token),)).fetchone()
        return row['id'] if row else None

    def request_id(self, owner, request):
        operation, key, fingerprint = request
        return str(uuid5(NAMESPACE_URL, owner+'\0'+operation+'\0'+key))

    def replay(self, owner, kind, request):
        if request is None:
            return None
        record=self.get(self.request_id(owner,request),owner,'request_receipt')
        if record is None:
            return None
        if record['fingerprint'] != request[2]:
            raise RequestConflict()
        result=self.get(record['object_id'],owner,kind)
        if result is None:
            raise RequestConflict()
        return result

    def create(self, owner, kind, payload, parent=None, links=None, request=None):
        oid, date = str(uuid4()), now()
        integrity_errors=(sqlite3.IntegrityError,)
        if self.mysql:
            import pymysql
            integrity_errors+=(pymysql.IntegrityError,)
        try:
            with self.connect() as db:
                if request is not None:
                    # The existing primary key serializes competing retries in the same transaction.
                    # Keep the receipt after result deletion so a retry cannot resurrect deleted data.
                    receipt=json.dumps({'fingerprint':request[2],'object_id':oid},allow_nan=False)
                    db.execute('INSERT INTO objects VALUES(?,?,?,?,?,?)',
                               (self.request_id(owner,request),owner,'request_receipt',None,receipt,date))
                for relation, target in (links or {}).items():
                    target_kind = {'source_extraction_id':'extraction','previous_listing_id':'listing'}.get(relation)
                    found = db.execute('SELECT id FROM objects WHERE id=? AND owner=? AND kind=?',
                                       (target, owner, target_kind)).fetchone()
                    if not found or kind != 'listing':
                        raise InvalidReference('자료를 찾을 수 없습니다.')
                db.execute("INSERT INTO objects VALUES(?,?,?,?,?,?)", (oid,owner,kind,parent,json.dumps(payload,ensure_ascii=False,allow_nan=False),date))
                if kind == 'listing':
                    maintenance_storage.project(db, oid, payload)
                for relation, target in (links or {}).items():
                    db.execute('INSERT INTO object_links VALUES(?,?,?)', (oid, relation, target))
        except integrity_errors:
            # The failed transaction is fully rolled back before reading the winner.
            replayed=self.replay(owner,kind,request)
            if replayed is None:
                raise
            return replayed
        return self.get(oid, owner, kind)

    def maintenance(self, listing_id, owner):
        with self.connect() as db:
            return maintenance_storage.read(db, listing_id, owner)

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
            total=db.execute('SELECT COUNT(*) AS total FROM objects WHERE parent=? AND owner=? AND kind=?',
                             (parent,owner,kind)).fetchone()['total']
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
