"""A running HTTP process is not ready when persistent storage is unavailable."""
import sqlite3

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.db import Store, mysql_options
from backend.app.main import create_app


def test_ready_checks_schema_and_recovers_without_process_restart(tmp_path):
    settings = Settings(db_path=tmp_path / 'ready.sqlite3')
    with TestClient(create_app(settings, pool=object())) as client:
        assert client.get('/ready').json() == {'status': 'ready'}
        with client.app.state.store.connect() as db:
            db.execute('DROP TABLE object_links')
        assert client.get('/health').status_code == 200
        response = client.get('/ready')
        assert response.status_code == 503
        assert response.json() == {'detail': 'DB에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'}
        Store(settings.db_path)
        assert client.get('/ready').status_code == 200


def test_ready_sanitizes_connection_errors_and_retains_missing_data_contract(tmp_path, monkeypatch):
    with TestClient(create_app(Settings(db_path=tmp_path / 'db', clean_csv=tmp_path / 'missing'))) as client:
        assert client.get('/ready').json() == {'detail': '정제된 실거래 데이터를 연결해야 합니다.'}
        def unavailable(**kwargs):
            raise sqlite3.OperationalError('private-host secret-password private-path')
        with monkeypatch.context() as patch:
            patch.setattr(client.app.state.store, 'connect', unavailable)
            response = client.get('/ready')
            assert response.status_code == 503
            assert 'private' not in response.text
            assert 'secret' not in response.text
        assert client.get('/ready').json() == {'detail': '정제된 실거래 데이터를 연결해야 합니다.'}


def test_mysql_readiness_timeout_and_connection_failure(monkeypatch):
    import pymysql
    store = Store.__new__(Store)
    store.mysql = True
    store.options = mysql_options('mysql://user:private-password@localhost/test')
    captured = {}
    def unavailable(**options):
        captured.update(options)
        raise pymysql.OperationalError(2003, 'private connection information')
    monkeypatch.setattr(pymysql, 'connect', unavailable)
    assert store.available() is False
    assert captured['connect_timeout'] == captured['read_timeout'] == captured['write_timeout'] == 2
    assert store.options['read_timeout'] == 30
