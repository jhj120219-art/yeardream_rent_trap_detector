import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.db import Store
from backend.tests.test_backend import payload, setup, raw_rows
from backend.tests.test_mysql_persistence import target, server
from backend.scripts.import_data import import_raw


def quoted_input():
    body=payload()
    body['options'].update(maintenance_10k_krw=7, electricity_in_maintenance='SEPARATE_CHARGE',
        electricity_10k_krw=None, water_in_maintenance='INCLUDED',water_10k_krw=1,
        internet_status='AVAILABLE',cleaning_in_maintenance='INCLUDED',cleaning_10k_krw=0,
        common_in_maintenance='UNKNOWN',other_in_maintenance='SEPARATE_CHARGE',
        other_cost_label='주차',other_10k_krw=3,maintenance_note='광고에 전기 별도, 수도 포함이라고 표시됨')
    return body


def test_shared_hold_preserves_advertisement_but_not_estimates(tmp_path):
    settings=Settings(db_path=tmp_path/'db',clean_csv=tmp_path/'missing',maintenance_enabled=False)
    with TestClient(create_app(settings)) as c:
        c.headers['Authorization']='Bearer '+c.post('/sessions').json()['token']
        body=quoted_input();lid=c.post('/listings',json=body).json()['id']
        report=c.get('/listings/'+lid+'/report').json()
        assert report['maintenance']=={'state':'ON_HOLD'}
        assert report['monthly_cost']=={'state':'ON_HOLD'}
        quote=report['advertised_costs'];items={x['item']:x for x in quote['items']}
        assert quote['state']=='USER_CONFIRMED' and quote['maintenance_10k_krw']==7
        assert items['ELECTRICITY']['quoted_monthly_10k_krw'] is None
        assert items['WATER']['quoted_monthly_10k_krw']==1
        assert len(items)==5
        legacy={x['item']:x for x in items['OTHER']['legacy_components']}
        assert legacy['CLEANING']['quoted_monthly_10k_krw']==0
        assert items['INTERNET']['status']=='UNKNOWN' # Availability is not inclusion.
        assert legacy['OTHER']['label']=='주차'
        assert legacy['OTHER']['quoted_monthly_10k_krw']==3
        assert items['OTHER']['quoted_monthly_10k_krw'] is None
        assert quote['comparison_state']=='ON_HOLD'
        assert c.get('/listings/'+lid).json()['input']['options']==body['options']
        c.headers['Authorization']='Bearer '+c.post('/sessions').json()['token']
        assert c.get('/listings/'+lid+'/report').status_code==404


@pytest.mark.parametrize('field,value',[
    ('water_10k_krw',-1),('gas_10k_krw',True),('common_10k_krw','NaN'),
    ('internet_10k_krw','미기재'),('cleaning_in_maintenance','YES'),
    ('maintenance_note',123),('other_cost_label',False),('water_in_maintenance',[])])
def test_invalid_advertisement_fields_rejected(setup,field,value):
    c,_=setup;body=quoted_input();body['options'][field]=value
    assert c.post('/listings',json=body).status_code==422


def test_quote_does_not_change_rent_or_confirm_unreviewed_input(setup):
    c,_=setup
    def run(body):
        lid=c.post('/listings',json=body).json()['id']
        return c.post('/listings/'+lid+'/analyses').json()['result'],c.get('/listings/'+lid+'/report').json()
    original,_=run(payload());changed,report=run(quoted_input())
    for key in ('status','stage','sample_count','prices_10k_krw','rent_difference_pct','price_label'):
        assert original[key]==changed[key]
    body=quoted_input();body['confirmation']['user_confirmed']=False
    result,report=run(body)
    assert result['status']=='INPUT_REVIEW_REQUIRED'
    assert report['advertised_costs']['state']=='NEEDS_USER_CONFIRMATION'


def test_advertisement_survives_http_restart(target,tmp_path):
    path,url=target
    raw=tmp_path/'raw.csv';clean=tmp_path/'clean.csv'
    raw_rows().to_csv(raw,index=False);import_raw(raw,clean)
    auth={}
    try:
        with server(path,url,clean,tmp_path) as c:
            auth={'Authorization':'Bearer '+c.post('/sessions').json()['token']};c.headers.update(auth)
            lid=c.post('/listings',json=quoted_input()).json()['id']
            quote=c.get('/listings/'+lid+'/report').json()['advertised_costs']
        with server(path,url,clean,tmp_path) as c:
            c.headers.update(auth)
            assert c.get('/listings/'+lid+'/report').json()['advertised_costs']==quote
    finally:
        if auth:
            store=Store(path,database_url=url,initialize=False)
            owner=store.owner(auth['Authorization'][7:])
            if owner:store.delete_session(owner)
