"""Never let the normal regression suite connect to a developer's production DB."""
import pytest


@pytest.fixture(autouse=True)
def isolated_database_environment(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('BACKEND_DB_PATH', raising=False)
