"""Never let the normal regression suite connect to a developer's production DB."""
import os
import pytest


@pytest.fixture(autouse=True)
def isolated_database_environment(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('BACKEND_DB_PATH', raising=False)


def pytest_addoption(parser):
    parser.addoption('--require-mysql', action='store_true',
                     help='Fail before tests if MYSQL_TEST_DATABASE_URL is missing')


def pytest_configure(config):
    if config.getoption('--require-mysql') and not os.getenv('MYSQL_TEST_DATABASE_URL'):
        raise pytest.UsageError('--require-mysql needs MYSQL_TEST_DATABASE_URL for an isolated test database')
