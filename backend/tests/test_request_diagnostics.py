import logging
import re
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.config import Settings


def test_correlation_cors_and_private_logs(tmp_path, caplog):
    secret = 'secret-team-value-' * 4
    keyfile = tmp_path / 'key'
    keyfile.write_text(secret)
    app = create_app(Settings(db_path=tmp_path/'db.sqlite3', clean_csv=tmp_path/'missing',
        shared_mode=True, team_key_file=str(keyfile), maintenance_enabled=False))
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    with TestClient(app) as client:
        denied = client.get('/private-address-token?password=secret-query', headers={
            'Authorization':'Bearer secret-bearer', 'X-Request-ID':'attacker-value',
            'Origin':'http://localhost:5173'})
        assert denied.status_code == 401
        assert re.fullmatch('[0-9a-f]{32}', denied.headers['x-request-id'])
        assert denied.headers['access-control-allow-origin'] == 'http://localhost:5173'
        assert 'X-Request-ID' in denied.headers['access-control-expose-headers']
        preflight = client.options('/sessions', headers={'Origin':'http://localhost:5173',
            'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'X-Team-Key'})
        assert preflight.status_code == 200
        assert preflight.headers['x-request-id'] != denied.headers['x-request-id']
        health = client.get('/health', headers={'X-Team-Key':secret})
        assert health.status_code == 200
        unknown = client.get('/private-address-token', headers={'X-Team-Key':secret})
        assert unknown.status_code == 404
    logs = '\n'.join(r.getMessage() for r in caplog.records if r.name == 'uvicorn.error')
    assert denied.headers['x-request-id'] in logs
    assert 'route=/health status=200' in logs
    assert 'route=/unmatched status=404' in logs
    for private in [secret,'private-address-token','secret-query','secret-bearer','attacker-value']:
        assert private not in logs
