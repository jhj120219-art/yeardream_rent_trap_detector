import copy
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.analysis_v2 import V2Service,load_cache
from backend.scripts.import_data import import_raw
from backend.tests.test_backend import payload,raw_rows
from backend.tests.test_mysql_persistence import target,server


def files(tmp_path,mixed=False,cache=True):
    raw=raw_rows(12)
    if mixed:
        other=raw.copy();other['BLDG_USG']='오피스텔';other['RTFE']='250'
        raw=pd.concat([raw,other],ignore_index=True)
    source=tmp_path/'raw.csv';clean=tmp_path/'clean.csv'
    raw.to_csv(source,index=False);import_raw(source,clean)
    path=tmp_path/'cache.csv'
    if cache:
        pd.DataFrame([dict(CGG_CD='11620',STDG_CD='10100',MNO='1',SNO='0',ok='True',n_main='1')]).to_csv(path,index=False)
    return clean,path


def input_body():
    return payload(rent_10k_krw=50,main_no='1',sub_no='0')


def test_verified_same_building_isolates_usage_and_holds_border(tmp_path):
    clean,cache=files(tmp_path,mixed=True)
    engine=V2Service(clean,cache)
    result=engine.run(input_body())
    assert result['stage']==0
    assert result['sample_count']==12
    assert result['prices_10k_krw']['median']<60 # Must not mix 250-만원 officetels at same lot.
    assert result['reference']['conditions']['scope_code']=='SAME_LOT_VERIFIED_SINGLE_MAIN'
    assert isinstance(result['warning_texts'],dict)
    assert result['reference']['contract_type']=='NEW'
    # Analyst margin policy: just above Q90 remains a held border.
    border=input_body();border['listing']['rent_10k_krw']=result['prices_10k_krw']['q90']*1.01
    held=engine.run(border)
    assert held['status']=='REFERENCE_ONLY'
    assert held['price_label']=='UNRATED'
    assert held['reason_codes']==['BORDER_MARGIN']
    assert held['percentile'] is None # The internal engine does not return this value.


def test_unverified_building_falls_back_without_fake_single_building(tmp_path):
    clean,cache=files(tmp_path,cache=False)
    engine=V2Service(clean,cache)
    result=engine.run(input_body())
    assert result['stage']!=0
    assert result['analysis_engine']['stage0_reason']=='BUILDING_UNVERIFIED'
    assert result['analysis_engine']['building_cache_status']=='MISSING'
    assert 'BUILDING_CACHE_UNAVAILABLE' in result['warnings']
    changed=input_body();changed['confirmation']['user_confirmed']=False
    assert engine.run(changed)['status']=='INPUT_REVIEW_REQUIRED'
    changed=input_body();changed['listing'].update(area_basis='SUPPLY')
    held=engine.run(changed)
    assert held['status']=='REFERENCE_ONLY' and held['price_label']=='UNRATED'
    changed=input_body();changed['listing']['rent_10k_krw']=500
    assert engine.run(changed)['status']=='INPUT_REVIEW_REQUIRED'


def test_failed_and_conflicting_building_records_are_not_trusted(tmp_path):
    path=tmp_path/'cache.csv'
    base=dict(CGG_CD='11620',STDG_CD='10100',MNO='1',SNO='0',n_main='1')
    pd.DataFrame([{**base,'ok':'False'}]).to_csv(path,index=False)
    assert load_cache(path)==({},'EMPTY')
    pd.DataFrame([{**base,'ok':'True'},{**base,'ok':'True','n_main':'2'}]).to_csv(path,index=False)
    with pytest.raises(ValueError):load_cache(path)


def test_v2_default_and_v1_compatibility_store_and_report(tmp_path):
    clean,cache=files(tmp_path)
    settings=Settings(db_path=tmp_path/'db',clean_csv=clean,analysis_engine='v2',building_cache=str(cache))
    with TestClient(create_app(settings)) as client:
        assert client.get('/ready').status_code==200
        assert client.get('/capabilities').json()['v2_status']=='READY'
        client.headers['Authorization']='Bearer '+client.post('/sessions').json()['token']
        lid=client.post('/listings',json=input_body()).json()['id']
        route='/listings/'+lid+'/analyses'
        headers={'Idempotency-Key':'v2-analysis-once'}
        result=client.post(route,headers=headers)
        assert result.status_code==201
        assert result.json()['result']['stage']==0
        assert client.post(route,headers=headers).json()==result.json()
        assert client.get('/listings/'+lid+'/report').json()['rent']['result']==result.json()['result']
        assert client.post(route+'?engine=v1',headers=headers).status_code==409
        assert 'analysis_engine' not in client.post(route+'?engine=v1').json()['result']
        for changes in ({'main_no':'12-3'},{'main_no':'0'},{'main_no':None,'sub_no':'2'}):
            body=input_body();body['listing'].update(changes)
            assert client.post('/listings',json=body).status_code==422
    missing=Settings(db_path=tmp_path/'missingdb',clean_csv=tmp_path/'missing',analysis_engine='v2')
    with TestClient(create_app(missing)) as client:
        assert client.get('/ready').status_code==503


def test_v2_result_persists_after_http_restart_on_real_storage(target,tmp_path,monkeypatch):
    path,url=target
    clean,cache=files(tmp_path)
    monkeypatch.setenv('V2_ENABLED','true')
    monkeypatch.setenv('BUILDING_CACHE_CSV',str(cache))
    auth={}
    try:
        with server(path,url,clean,tmp_path) as client:
            auth={'Authorization':'Bearer '+client.post('/sessions').json()['token']};client.headers.update(auth)
            lid=client.post('/listings',json=input_body()).json()['id']
            response=client.post('/listings/'+lid+'/analyses?engine=v2')
            assert response.status_code==201
            saved=response.json();assert saved['result']['stage']==0
        with server(path,url,clean,tmp_path) as client:
            client.headers.update(auth)
            assert client.get('/analyses/'+saved['id']).json()==saved
            assert client.get('/listings/'+lid+'/report').json()['rent']['result']==saved['result']
    finally:
        if auth:
            from backend.app.db import Store
            store=Store(path,database_url=url,initialize=False)
            owner=store.owner(auth['Authorization'][7:])
            if owner:store.delete_session(owner)
