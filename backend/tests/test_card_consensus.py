import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app


@pytest.fixture
def client(tmp_path):
    s = Settings(db_path=tmp_path / 'db.sqlite3', clean_csv=tmp_path / 'none.csv')
    with TestClient(create_app(s)) as c:
        c.headers['Authorization'] = 'Bearer ' + c.post('/sessions').json()['token']
        yield c


def read(dep=1000, rent=55, area=19.83, maint=10, kind='월세'):
    return dict(contract_type=kind, deposit_10k_krw=dep, rent_10k_krw=rent, area_m2=area, maintenance_10k_krw=maint)


def test_only_values_read_identically_by_two_engines_are_filled(client):
    body = {'engine_reads': {'qwen': [read(), read(500, 40, 23.14, 8)], 'paddle': [read()], 'easy': [read(), read(15000, None, 30, 12, '전세')]}}
    r = client.post('/extraction/card-consensus', json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out['summary'] == {'extracted': 1, 'partial': 0, 'needs_review': 0, 'on_hold': 2}
    filled = [c for c in out['cards'] if c['status'] == 'extracted']
    assert filled[0]['fields']['deposit_10k_krw']['value'] == 1000 and filled[0]['user_confirmed'] is False
    assert all(v['value'] is None for c in out['cards'] if c['status'] == 'on_hold' for v in c['fields'].values())


def test_conflicting_amounts_need_review_and_never_fill(client):
    out = client.post('/extraction/card-consensus', json={'engine_reads': {'a': [read(1000, 40, 23.14, 8)], 'b': [read(500, 40, 23.14, 8)]}}).json()
    assert out['summary'] == {'extracted': 0, 'partial': 0, 'needs_review': 1, 'on_hold': 0}
    assert out['cards'][0]['fields']['deposit_10k_krw']['value'] is None and len(out['cards'][0]['candidates']) == 2


def test_warning_is_attached_without_changing_value(client):
    out = client.post('/extraction/card-consensus', json={'engine_reads': {'a': [read(area=201)], 'b': [read(area=201)]}}).json()
    c = out['cards'][0]
    assert c['status'] == 'extracted' and 'AREA_OVER_100_M2' in c['warnings'] and c['fields']['area_m2']['value'] == 201


@pytest.mark.parametrize('body', [
    {'engine_reads': {'only': [read()]}},                                        # 엔진 2개 미만
    {'engine_reads': {'a': [read(dep=-1)], 'b': []}},
    {'engine_reads': {'a': [read(kind='매매')], 'b': []}},
    {'engine_reads': {'a': [dict(read(), surprise=1)], 'b': []}},
    {'engine_reads': {'a': [read(dep=True)], 'b': []}},
    {'engine_reads': {'a': [read(area=0)], 'b': []}},
    {'engine_reads': {'a': [], 'b': [], 'c': [], 'd': [], 'e': [], 'f': []}},   # 엔진 5개 초과
    {'extra': 1, 'engine_reads': {'a': [], 'b': []}},
])
def test_invalid_input_is_rejected(client, body):
    assert client.post('/extraction/card-consensus', json=body).status_code == 422


def test_requires_session(client):
    client.headers.pop('Authorization')
    assert client.post('/extraction/card-consensus', json={'engine_reads': {'a': [], 'b': []}}).status_code in (401, 403)
