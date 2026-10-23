from fastapi.testclient import TestClient
import httpx
from backend.app.public_gateway import create_gateway


def test_key_is_server_only_and_routes_are_limited(tmp_path):
    key = 'private-test-only-' * 4
    path = tmp_path / 'key'
    path.write_text(key)
    seen = []
    def upstream(request):
        seen.append(request)
        assert request.headers['x-team-key'] == key
        return httpx.Response(200, json={'token': 'test-session'})
    with TestClient(create_gateway(path, transport=httpx.MockTransport(upstream))) as c:
        assert key not in c.get('/public-config.json').text
        assert key not in c.get('/').text
        assert c.get('/.env').status_code == 404
        assert c.post('/sessions', headers={'Origin': 'https://evil.invalid'}).status_code == 403
        assert c.post('/sessions').json()['token'] == 'test-session'
        assert c.get('/sessions/current').status_code == 405
        assert c.post('/admin').status_code == 405
        assert len(seen) == 1
        assert c.post('/listings', content=b'x' * (9*1024*1024+1)).status_code == 413


def test_upstream_failure_is_generic(tmp_path):
    p = tmp_path / 'key'
    p.write_text('secret-' * 10)
    def fail(request):
        raise httpx.ConnectError('private address and key', request=request)
    with TestClient(create_gateway(p, transport=httpx.MockTransport(fail))) as c:
        response = c.get('/capabilities')
        assert response.status_code == 503
        assert 'private' not in response.text
