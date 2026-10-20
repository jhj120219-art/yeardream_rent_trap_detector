from pathlib import Path
"""Team v0.2 direct-input flow: real loaded region choices and existing v1.1 contract."""
import pandas as pd
from fastapi.testclient import TestClient
from backend.app.analysis_service import location_catalog
from backend.app.config import Settings, ROOT
from backend.app.main import create_app
from backend.tests.test_backend import setup, payload


def test_loaded_region_catalog_and_dong_name_input(setup):
    client,_=setup
    catalog=client.get('/locations').json()
    assert catalog['source']=='LOADED_NEW_RENT_CONTRACTS'
    district=catalog['districts'][0]
    assert (district['district_code'],district['district_name'])==('11620','관악구')
    assert district['dongs']==[{'legal_dong_code':'1162010100','dong_name':'봉천동','new_contract_count':40}]
    assert client.get('/locations?district_code=11620').json()['districts']==[district]
    assert client.get('/locations?district_code=11110').status_code==404
    assert client.get('/locations?district_code=123').status_code==422
    body=payload()
    body['listing'].pop('legal_dong_code')
    body['listing']['dong']='봉천동'
    body['listing']['address_text']=None
    saved=client.post('/listings',json=body)
    assert saved.status_code==201
    analyzed=client.post('/listings/'+saved.json()['id']+'/analyses')
    assert analyzed.json()['result']['status']=='COMPARED'
    # Editing creates a new linked listing; the original input/analysis stays unchanged.
    revised=payload(rent_10k_krw=70)
    revised['previous_listing_id']=saved.json()['id']
    changed=client.post('/listings',json=revised)
    assert changed.status_code==201
    assert changed.json()['links']['previous_listing_id']==saved.json()['id']
    assert client.get('/listings/'+saved.json()['id']).json()['input']==saved.json()['input']
    assert client.get('/listings/'+changed.json()['id']+'/report').json()['rent']['analysis_id'] is None


def test_catalog_is_new_only_and_keeps_same_named_dongs_distinct():
    frame=pd.DataFrame([
        {'CGG_CD':'11620','STDG_CD':'10100','dong':'동일명','is_new':'True'},
        {'CGG_CD':'11620','STDG_CD':'10200','dong':'동일명','is_new':'True'},
        {'CGG_CD':'11620','STDG_CD':'10300','dong':'갱신만','is_new':'False'},
        {'CGG_CD':'11110','STDG_CD':'10100','dong':'범위밖','is_new':'True'}])
    districts=location_catalog(frame)
    assert len(districts)==1
    assert [x['legal_dong_code'] for x in districts[0]['dongs']]==['1162010100','1162010200']
    assert districts[0]['new_contract_count']==2


def test_missing_data_does_not_invent_region_choices(tmp_path):
    with TestClient(create_app(Settings(db_path=tmp_path/'db',clean_csv=tmp_path/'missing'))) as client:
        assert client.get('/locations').status_code==503
        assert client.get('/capabilities').json()['location_catalog_available'] is False


def test_team_v11_source_matches_current_runtime_bridge():
    # Fail visibly if a later ZIP changes analysis policy before explicit adapter review.
    for name in ('analyze.py','normalize_listing.py','compare_rent.py'):
        import importlib
        assert Path(importlib.import_module(name[:-3]).__file__).resolve()==(ROOT/'machine'/name).resolve()
