"""실행 중 발견한 입력·데이터·외부 응답 경계의 회귀 검증."""
import asyncio

import httpx
import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.analysis_service import load_pool
from backend.app.config import Settings
from backend.app.main import create_app
from backend.tests.test_backend import payload, raw_rows, setup, submit
from backend.scripts.import_data import import_raw


@pytest.mark.parametrize('change', [
    {'floor': 5.9}, {'built_year': 2005.7}, {'total_floors': 4.2},
    {'floor': True}, {'rent_10k_krw': True}, {'area_m2': False},
    {'district_code': 11620}, {'legal_dong_code': '116201010'},
    {'legal_dong_code': '1144010100'}, {'floor': 5, 'total_floors': 4},
    {'floor': 5, 'floor_type': 'BASEMENT'}, {'floor': -1, 'floor_type': 'GROUND'},
    {'built_year': 'invalid'}, {'built_year': 1949},
])
def test_invalid_input_cannot_be_silently_changed(setup, change):
    response = setup[0].post('/listings', json=payload(**change))
    assert response.status_code == 422
    assert 'input' not in response.json()['detail'][0]


@pytest.mark.parametrize('value', [-1, True, 'invalid'])
def test_management_cost_validation(setup, value):
    body = payload()
    body['options']['maintenance_10k_krw'] = value
    assert setup[0].post('/listings', json=body).status_code == 422


def test_coverage_reports_only_loaded_data_and_missing_features(setup):
    data = setup[0].get('/capabilities').json()
    assert data['data_status'] == 'READY'
    assert data['loaded_coverage'] == [dict(gu='관악구', usage='아파트', basement=False, new_contract_count=40)]
    assert data['same_building_first'] is False
    assert data['comparable_transactions_available'] is False
    _, response = submit(setup[0], payload())
    result = response.json()['result']
    assert result['reference']['conditions']
    assert result['prices_10k_krw']['median'] == 50
    # 차이율의 단위는 기존 분석 계약 그대로: 0.6 = 60%.
    assert result['rent_difference_pct'] == 0.6


@pytest.mark.parametrize('column,value', [
    ('area', '-1'), ('rent', '0'), ('dep', '-100'),
    ('CGG_CD', '1162'), ('STDG_CD', 'abcde'), ('gu', ''),
    ('dong', ''), ('usage', ''), ('arch', 'Infinity'), ('arch', '2005.5'),
])
def test_invalid_clean_data_does_not_become_ready(tmp_path, column, value):
    source, target = tmp_path/'raw.csv', tmp_path/'clean.csv'
    raw_rows().to_csv(source, index=False)
    import_raw(source, target)
    frame = pd.read_csv(target, dtype=str)
    frame.loc[0, column] = value
    frame.to_csv(target, index=False)
    with pytest.raises(ValueError):
        load_pool(target)
    with TestClient(create_app(Settings(db_path=tmp_path/'db', clean_csv=target))) as client:
        assert client.get('/health').json()['data_status'] == 'INVALID'
        assert client.get('/ready').status_code == 503
        assert client.get('/capabilities').json()['loaded_coverage'] == []


@pytest.mark.parametrize('documents', [None, {}, 'invalid', [None]])
def test_malformed_address_provider_is_controlled(monkeypatch, documents):
    import backend.app.address as address
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, **kwargs):
            return httpx.Response(200, request=httpx.Request('GET', url), json={'documents': documents})
    monkeypatch.setattr(address.httpx, 'AsyncClient', Client)
    with pytest.raises(HTTPException) as error:
        asyncio.run(address.search_address('테스트', Settings(kakao_key='not-a-real-key')))
    assert error.value.status_code == 502
    assert 'not-a-real-key' not in error.value.detail


def test_extraction_ownership_and_session_deletion(tmp_path):
    from backend.tests.test_backend import png
    async def fake(data, settings): return {'extraction_status': 'NEEDS_REVIEW'}
    with TestClient(create_app(Settings(db_path=tmp_path/'db', clean_csv=tmp_path/'missing'), extractor=fake)) as client:
        owner = {'Authorization': 'Bearer '+client.post('/sessions').json()['token']}
        other = {'Authorization': 'Bearer '+client.post('/sessions').json()['token']}
        oid = client.post('/extractions', files={'file': ('x.png', png())}, headers=owner).json()['id']
        assert client.get('/extractions/'+oid, headers=other).status_code == 404
        assert client.delete('/extractions/'+oid, headers=other).status_code == 404
        assert client.delete('/sessions/current', headers=owner).status_code == 204
        assert client.get('/extractions/'+oid, headers=owner).status_code == 401


def test_unconfirmed_input_never_calls_price_analysis(setup, monkeypatch):
    import analyze
    def forbidden(*args, **kwargs):
        pytest.fail('未確認 input reached price analysis')
    monkeypatch.setattr(analyze, 'analyze_listing', forbidden)
    body = payload()
    body['confirmation']['user_confirmed'] = False
    _, response = submit(setup[0], body)
    assert response.json()['result']['status'] == 'INPUT_REVIEW_REQUIRED'


@pytest.mark.parametrize('mode', ['http_error', 'timeout', 'malformed', 'refusal', 'truncated'])
def test_vision_provider_failure_is_controlled(monkeypatch, mode):
    import backend.app.vision as vision
    from backend.tests.test_backend import png
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            request = httpx.Request('POST', url)
            if mode == 'timeout':
                raise httpx.ReadTimeout('not-a-real-key', request=request)
            body = {'choices': [{'finish_reason': 'length' if mode == 'truncated' else 'stop',
                                  'message': {'content': '{}', 'refusal': 'refused' if mode == 'refusal' else None}}]}
            return httpx.Response(500 if mode == 'http_error' else 200, request=request, json=body)
    monkeypatch.setattr(vision.httpx, 'AsyncClient', Client)
    with pytest.raises(HTTPException) as error:
        asyncio.run(vision.extract_image(png(), Settings(openai_key='not-a-real-key', vision_model='mock-only')))
    assert error.value.status_code == 502
    assert 'not-a-real-key' not in error.value.detail
