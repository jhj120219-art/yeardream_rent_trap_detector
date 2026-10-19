"""Persistence tests use synthetic inputs; MYSQL_TEST_DATABASE_URL must be a private test DB."""
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager

import httpx
import pytest

from backend.app.db import Store, mysql_options
from backend.scripts.migrate_mysql import snapshot, transfer
from backend.tests.test_backend import payload, raw_rows
from backend.scripts.import_data import import_raw


@pytest.fixture(params=['sqlite', 'mysql'])
def target(request, tmp_path):
    if request.param == 'mysql':
        url = os.getenv('MYSQL_TEST_DATABASE_URL', '')
        if not url:
            pytest.skip('MYSQL_TEST_DATABASE_URL unavailable: actual MySQL integration not verified')
        return None, url
    return tmp_path / 'app.sqlite3', ''


@contextmanager
def server(path, url, clean, tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, DATABASE_URL=url, BACKEND_DB_PATH=str(path) if path else '',
               RENT_CLEAN_CSV=str(clean), TEAM_SHARED_MODE='false', MAINTENANCE_ENABLED='true')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with (tmp_path / 'uvicorn.log').open('w', encoding='utf-8') as log:
        proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app.main:app',
                                 '--host', '127.0.0.1', '--port', str(port), '--no-access-log'],
                                env=env, stdout=log, stderr=log, creationflags=flags)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False) as client:
                for _ in range(100):
                    if proc.poll() is not None:
                        pytest.fail('Server exited; inspect private uvicorn.log')
                    try:
                        if client.get('/health').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(.1)
                else:
                    pytest.fail('Server startup timeout')
                yield client
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def test_http_process_restart_persists_input_and_analysis(target, tmp_path):
    path, url = target
    source, clean = tmp_path / 'raw.csv', tmp_path / 'clean.csv'
    raw_rows().to_csv(source, index=False)
    import_raw(source, clean)
    with server(path, url, clean, tmp_path) as c:
        auth = {'Authorization': 'Bearer ' + c.post('/sessions').json()['token']}
        c.headers.update(auth)
        body = payload()
        response = c.post('/listings', json=body)
        assert response.status_code == 201
        listing = response.json()
        lid = listing['id']
        assert c.get('/listings/' + lid).json() == listing
        assert listing['input']['listing']['address_text'] == body['listing']['address_text']
        assert listing['input']['listing']['unit_ho'] == '501'
        assert c.get('/listings/' + lid + '/report').json()['rent']['analysis_id'] is None
        response = c.post('/listings/' + lid + '/analyses')
        assert response.status_code == 201
        analysis = response.json()
        assert analysis['result']['status'] == 'COMPARED'
        assert c.get('/analyses/' + analysis['id']).json() == analysis
        store = Store(path, database_url=url)
        owner = store.owner(auth['Authorization'][7:])
        with store.connect() as db:
            rows = db.execute('SELECT kind,payload FROM objects WHERE owner=?', (owner,)).fetchall()
            assert sorted(row['kind'] for row in rows) == ['analysis', 'listing']
    # A different OS process opens fresh DB connections after the first process exits.
    with server(path, url, clean, tmp_path) as c:
        c.headers.update(auth)
        assert c.get('/listings/' + lid).json() == listing
        assert c.get('/analyses/' + analysis['id']).json() == analysis
        assert lid in [item['id'] for item in c.get('/listings').json()['items']]
        other = c.post('/sessions').json()['token']
        assert c.get('/listings/' + lid, headers={'Authorization': 'Bearer ' + other}).status_code == 404
        assert c.delete('/sessions/current', headers={'Authorization': 'Bearer ' + other}).status_code == 204
        assert c.delete('/listings/' + lid).status_code == 204
        assert c.get('/analyses/' + analysis['id']).status_code == 404
        assert c.delete('/sessions/current').status_code == 204


def test_migration_backup_values_links_and_nonempty_refusal(tmp_path, target):
    original = Store(tmp_path / 'source.sqlite3')
    token = original.session()
    owner = original.owner(token)
    extraction = original.create(owner, 'extraction', {'unicode': '한글 🏠'})
    listing = original.create(owner, 'listing', {'input': payload()}, links={'source_extraction_id': extraction['id']})
    analysis = original.create(owner, 'analysis', {'result': {'status': 'COMPARED'}}, parent=listing['id'])
    backup = snapshot(tmp_path / 'source.sqlite3', tmp_path / 'backup.sqlite3')
    path, url = target
    target = Store(path, database_url=url)
    assert transfer(backup, target) == {'sessions': 1, 'objects': 3, 'object_links': 1}
    assert target.owner(token) == owner
    assert target.get(listing['id'], owner, 'listing') == listing
    assert target.get(analysis['id'], owner, 'analysis') == analysis
    with pytest.raises(ValueError, match='empty'):
        transfer(backup, target)
    with pytest.raises(FileExistsError):
        snapshot(tmp_path / 'source.sqlite3', backup)
    assert original.get(listing['id'], owner, 'listing') == listing
    target.delete_session(owner)


def test_transaction_rollback(tmp_path):
    store = Store(tmp_path / 'rollback.sqlite3')
    with pytest.raises(RuntimeError):
        with store.connect() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?)', ('id', 'hash', 'date'))
            raise RuntimeError('abort')
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) AS total FROM sessions').fetchone()['total'] == 0


def test_mysql_configuration_and_no_silent_fallback():
    options = mysql_options('mysql+pymysql://user:p%40ss@localhost:3307/rent?ssl_ca=C%3A%2Fca.pem')
    assert options['password'] == 'p@ss'
    assert options['port'] == 3307
    assert options['charset'] == 'utf8mb4'
    assert options['autocommit'] is False
    assert options['ssl_verify_identity'] is True
    with pytest.raises(ValueError):
        Store()
    with pytest.raises(ValueError):
        Store(database_url='sqlite:///wrong')
    with pytest.raises(ValueError):
        mysql_options('mysql://user:pass@host/db?unknown=1')


def test_mysql_adapter_commit_rollback_and_parameters(monkeypatch):
    import pymysql
    calls = []

    class Cursor:
        def execute(self, query, args):
            calls.append((query, args))
        def close(self):
            calls.append('cursor closed')

    class Connection:
        def cursor(self):
            return Cursor()
        def commit(self):
            calls.append('commit')
        def rollback(self):
            calls.append('rollback')
        def close(self):
            calls.append('closed')

    monkeypatch.setattr(pymysql, 'connect', lambda **kwargs: Connection())
    store = Store(database_url='mysql://user:pass@localhost/test')
    assert sum('ENGINE=InnoDB' in item[0] for item in calls if isinstance(item, tuple)) == 3
    calls.clear()
    with store.connect() as db:
        db.execute('SELECT * FROM objects WHERE id=?', ('parameter',))
    assert calls == [('SELECT * FROM objects WHERE id=%s', ('parameter',)), 'commit', 'cursor closed', 'closed']
    calls.clear()
    with pytest.raises(RuntimeError):
        with store.connect() as db:
            db.execute('DELETE FROM objects WHERE id=?', ('parameter',))
            raise RuntimeError('abort')
    assert calls[-3:] == ['rollback', 'cursor closed', 'closed']


def test_migration_rolls_back_all_inserted_rows_on_bad_link(tmp_path, target):
    original = Store(tmp_path / 'source.sqlite3')
    token = original.session()
    owner = original.owner(token)
    listing = original.create(owner, 'listing', {'input': payload()})
    # Simulate corrupt historical input without changing production constraints.
    with sqlite3.connect(tmp_path / 'source.sqlite3') as connection:
        connection.execute('INSERT INTO object_links VALUES(?,?,?)',
                           (listing['id'], 'source_extraction_id', 'missing'))
    path, url = target
    destination = Store(path, database_url=url)
    try:
        transfer(tmp_path / 'source.sqlite3', destination)
    except Exception as error:
        assert error.__class__.__name__ == 'IntegrityError'
    else:
        pytest.fail('Invalid reference was accepted')
    with destination.connect() as connection:
        for table in ('sessions', 'objects', 'object_links'):
            assert connection.execute('SELECT COUNT(*) AS total FROM ' + table).fetchone()['total'] == 0
