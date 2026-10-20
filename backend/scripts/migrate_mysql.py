"""Offline, non-destructive SQLite -> empty MySQL migration.
Run from repository root: python -m backend.scripts.migrate_mysql --help
"""
import json
import argparse
import os
from pathlib import Path
import sqlite3

from backend.app.db import Store
from backend.app.maintenance_storage import project

TABLES = {
    'sessions': ('id', 'token_hash', 'created_at'),
    'objects': ('id', 'owner', 'kind', 'parent', 'payload', 'created_at'),
    'object_links': ('object_id', 'relation', 'target_id'),
}


def snapshot(source, backup):
    source, backup = Path(source).resolve(), Path(backup).resolve()
    if not source.is_file():
        raise ValueError('Source SQLite file does not exist')
    backup.parent.mkdir(parents=True, exist_ok=True)
    # Refuse overwrite, including source == backup.
    with backup.open('xb'):
        pass
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        with sqlite3.connect(backup) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('SQLite integrity check failed')
            if dst.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('SQLite foreign key check failed')
    return backup


def transfer(backup, target):
    """One target DML transaction; preserve IDs, hashes, payloads, dates and links."""
    with sqlite3.connect(Path(backup).resolve().as_uri() + '?mode=ro', uri=True) as src:
        src.row_factory = sqlite3.Row
        rows = {table: [dict(row) for row in src.execute('SELECT * FROM ' + table)] for table in TABLES}
    # Topological order supports analysis/evidence parents regardless of timestamp.
    pending = {row['id']: row for row in rows['objects']}
    ordered, seen = [], set()
    while pending:
        batch = [row for row in pending.values() if row['parent'] is None or row['parent'] in seen]
        if not batch:
            raise ValueError('Missing or cyclic object parent')
        for row in batch:
            ordered.append(row)
            seen.add(row['id'])
            del pending[row['id']]
    rows['objects'] = ordered
    with target.connect() as db:
        for table in TABLES:
            if db.execute('SELECT COUNT(*) AS total FROM ' + table).fetchone()['total']:
                raise ValueError('Target must be empty; nothing was overwritten')
        for table, columns in TABLES.items():
            for row in rows[table]:
                db.execute('INSERT INTO ' + table + ' (' + ','.join(columns) + ') VALUES (' +
                           ','.join('?' for _ in columns) + ')', tuple(row[col] for col in columns))
            actual = [tuple(row[col] for col in columns) for row in db.execute('SELECT * FROM ' + table).fetchall()]
            expected = [tuple(row[col] for col in columns) for row in rows[table]]
            if sorted(actual, key=repr) != sorted(expected, key=repr):
                raise ValueError('Migration verification failed; rolling back')
        for row in rows['objects']:
            if row['kind'] == 'listing':
                project(db, row['id'], json.loads(row['payload']))
    return {table: len(data) for table, data in rows.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True, help='New private backup path (never overwritten)')
    parser.add_argument('--offline-confirmed', action='store_true', help='Both source and target applications are stopped')
    args = parser.parse_args()
    if not args.offline_confirmed:
        parser.error('Stop both applications and pass --offline-confirmed')
    url = os.getenv('DATABASE_URL', '')
    if not url:
        parser.error('Set DATABASE_URL for the target MySQL database')
    backup = snapshot(args.source, args.backup)
    counts = transfer(backup, Store(database_url=url))
    print('Verified migration counts:', counts)


if __name__ == '__main__':
    main()
