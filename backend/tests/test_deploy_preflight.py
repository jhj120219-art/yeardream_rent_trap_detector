"""Deployment preflight never initializes schema or exposes private connection errors."""
import json
import os
from pathlib import Path

import pytest

from backend.app.config import Settings
from backend.app.db import Store
from backend.scripts import deploy_preflight as preflight
from backend.tests.test_backend import raw_rows
from backend.scripts.import_data import import_raw


@pytest.fixture
def configured(tmp_path):
    key = tmp_path / 'team.key'
    key.write_text('x' * 64)
    raw, clean = tmp_path / 'raw.csv', tmp_path / 'clean.csv'
    raw_rows().to_csv(raw, index=False)
    import_raw(raw, clean)
    return Settings(database_url='mysql://app:private-password@db.private/rent', db_auto_init=False,
                    shared_mode=True, team_key_file=str(key), clean_csv=clean,
                    cors_origins=['https://frontend.test.invalid'], maintenance_enabled=False)


def test_configuration_only_never_claims_connection(configured, monkeypatch):
    monkeypatch.setattr(preflight, 'check_database', lambda *args: pytest.fail('Must not connect'))
    report, code = preflight.run(configured, no_connect=True)
    assert code == 2
    assert report['status'] == 'incomplete'
    assert all(row['status'] == 'ok' for row in report['checks'])
    assert 'private-password' not in json.dumps(report)


@pytest.mark.parametrize('origin', ['*', 'http://frontend.test', 'https://example.com',
                                  'https://user:password@site.test', 'https://site.test/path',
                                  'https://site.test?key=secret', 'https://site.test:invalid'])
def test_bad_deployment_origins_rejected(configured, origin):
    configured.cors_origins = [origin]
    report, code = preflight.run(configured, no_connect=True)
    assert code == 1
    assert next(item for item in report['checks'] if item['check'] == 'frontend_origins')['status'] == 'failed'
    assert origin not in json.dumps(report)


def test_missing_production_inputs_fail_without_db_writes(tmp_path, monkeypatch):
    settings = Settings(clean_csv=tmp_path/'absent')
    monkeypatch.setattr(preflight, 'check_database', lambda *args: pytest.fail('Must not connect'))
    report, code = preflight.run(settings)
    assert code == 1
    assert report['status'] == 'blocked'
    assert all(item['status'] == 'failed' for item in report['checks'])


def test_mysql_driver_errors_are_redacted(monkeypatch):
    import pymysql
    def fail(**kwargs):
        raise pymysql.OperationalError(2003, 'sensitive-password host=private.internal')
    monkeypatch.setattr(pymysql, 'connect', fail)
    report = preflight.check_database('mysql://app:sensitive-password@private.internal/rent')
    assert report[0]['status'] == 'failed'
    assert 'sensitive' not in json.dumps(report)
    assert 'private.internal' not in json.dumps(report)


def test_initialization_disabled_does_not_connect_or_create_files(tmp_path, monkeypatch):
    monkeypatch.setattr(Store, 'connect', lambda *args, **kwargs: pytest.fail('Unexpected DB initialization'))
    Store(database_url='mysql://app:password@host/db', initialize=False)
    Store(tmp_path / 'missing' / 'app.sqlite3', initialize=False)
    assert not (tmp_path / 'missing').exists()


def test_actual_mysql_readonly_preflight():
    url = os.getenv('MYSQL_TEST_DATABASE_URL', '')
    if not url:
        pytest.skip('Actual MySQL deployment preflight requires MYSQL_TEST_DATABASE_URL')
    store = Store(database_url=url)
    def counts():
        with store.connect() as db:
            return [db.execute('SELECT COUNT(*) AS total FROM ' + table).fetchone()['total']
                    for table in ('sessions', 'objects', 'object_links')]
    before = counts()
    checks = preflight.check_database(url, allow_private_network=True)
    assert all(item['status'] == 'ok' for item in checks), checks
    strict = preflight.check_database(url)
    assert next(item for item in strict if item['check'] == 'database_transport')['status'] == 'failed'
    assert counts() == before
