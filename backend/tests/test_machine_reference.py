"""Analyst integration and persistence; synthetic listing, no accuracy claims."""
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.db import Store
from backend.app.machine_reference import ReferenceScenario, ReferenceUnavailable, run_worker
from backend.tests.test_backend import payload, raw_rows, setup
from backend.tests.test_maintenance_selection import checkbox_options
from backend.tests.test_mysql_persistence import target, server
from backend.scripts.import_data import import_raw


def test_default_off_and_global_hold(setup):
    client, settings = setup
    lid=client.post('/listings',json=payload()).json()['id']
    assert client.post(f'/listings/{lid}/maintenance-references',json={'target_month':10}).status_code==503
    assert client.get('/capabilities').json()['machine_maintenance_enabled'] is False
    settings.machine_maintenance_enabled=True
    settings.maintenance_enabled=False
    assert client.post(f'/listings/{lid}/maintenance-references',json={'target_month':10}).status_code==503


def test_unavailable_worker_returns_no_private_details(tmp_path):
    with pytest.raises(ReferenceUnavailable):
        run_worker({},tmp_path/'not-installed')


def test_input_checks_precede_worker(setup,monkeypatch):
    client,settings=setup;settings.machine_maintenance_enabled=True
    def forbidden(*args):
        pytest.fail('Worker must not run before valid confirmed checkbox input')
    monkeypatch.setattr('backend.app.main.calculate_reference',forbidden)
    body=payload();body['options']=checkbox_options()
    body['confirmation']['user_confirmed']=False
    lid=client.post('/listings',json=body).json()['id']
    scenario={'target_month':10,'acknowledge_reference_limits':True}
    assert client.post(f'/listings/{lid}/maintenance-references',json=scenario).status_code==422
    body['confirmation']['user_confirmed']=True
    lid=client.post('/listings',json=body).json()['id']
    assert client.post(f'/listings/{lid}/maintenance-references',json={'target_month':10}).status_code==422
    assert client.post(f'/listings/{lid}/maintenance-references',json={**scenario,'household_size':True}).status_code==422


def test_real_analyst_persistence_and_owner_isolation(target,tmp_path):
    root=os.getenv('MAINTENANCE_INTEGRATION_ROOT')
    if not root:
        pytest.skip('Separate analyst checkout and real reference CSV required')
    path,url=target
    source=tmp_path/'raw.csv';clean=tmp_path/'clean.csv'
    raw_rows().to_csv(source,index=False);import_raw(source,clean)
    settings=Settings(db_path=path,database_url=url,clean_csv=clean,
                      machine_maintenance_enabled=True,maintenance_machine_root=root)
    owner=None;other=None
    try:
        with TestClient(create_app(settings)) as client:
            token=client.post('/sessions').json()['token'];client.headers['Authorization']='Bearer '+token
            owner=client.app.state.store.owner(token)
            body=payload();body['options']=checkbox_options()
            lid=client.post('/listings',json=body).json()['id']
            scenario={'target_month':10,'household_size':1,'metering':'INDIVIDUAL','acknowledge_reference_limits':True}
            response=client.post(f'/listings/{lid}/maintenance-references',json=scenario,headers={'Idempotency-Key':'reference-test-0001'})
            assert response.status_code==201,response.text
            saved=response.json();rid=saved['id']
            assert saved['result']['errors']==[]
            assert saved['result']['decomposition']['enabled'] is False
            assert saved['result']['items']['OTHER']['advertised_amount_krw'] is None
            assert saved['groups']['state']=='PARTIAL_REFERENCE'
            assert saved['groups']['selected']['reference_low_total_krw'] is None
            assert 'OTHER' in saved['groups']['selected']['missing_items']
            assert any(row['reference_state']=='AVAILABLE' for group in ('selected','unselected') for row in saved['groups'][group]['items'])
            assert client.post(f'/listings/{lid}/maintenance-references',json=scenario,headers={'Idempotency-Key':'reference-test-0001'}).json()['id']==rid
            assert client.post(f'/listings/{lid}/maintenance-references',json={**scenario,'target_month':11},headers={'Idempotency-Key':'reference-test-0001'}).status_code==409
            report=client.get(f'/listings/{lid}/report').json()
            assert report['maintenance_reference_groups']==saved['groups']
            assert report['machine_maintenance_reference']==saved
            other_token=client.post('/sessions').json()['token'];other=client.app.state.store.owner(other_token)
            client.headers['Authorization']='Bearer '+other_token
            assert client.get('/maintenance-references/'+rid).status_code==404
            assert client.post(f'/listings/{lid}/maintenance-references',json=scenario).status_code==404
        with TestClient(create_app(settings)) as reopened:
            reopened.headers['Authorization']='Bearer '+token
            assert reopened.get('/maintenance-references/'+rid).json()==saved
            assert reopened.get(f'/listings/{lid}/report').json()['maintenance_reference_groups']==saved['groups']
    finally:
        store=Store(path,database_url=url,initialize=False)
        for sid in (owner,other):
            if sid:store.delete_session(sid)


def test_real_http_restart_retains_reference(target,tmp_path,monkeypatch):
    root=os.getenv('MAINTENANCE_INTEGRATION_ROOT')
    if not root:
        pytest.skip('Separate analyst checkout and real reference CSV required')
    monkeypatch.setenv('MACHINE_MAINTENANCE_ENABLED','true')
    monkeypatch.setenv('MAINTENANCE_MACHINE_ROOT',root)
    path,url=target
    source=tmp_path/'raw.csv';clean=tmp_path/'clean.csv'
    raw_rows().to_csv(source,index=False);import_raw(source,clean)
    store=Store(path,database_url=url);owner=None
    try:
        with server(path,url,clean,tmp_path) as client:
            token=client.post('/sessions').json()['token'];owner=store.owner(token)
            client.headers['Authorization']='Bearer '+token
            body=payload();body['options']=checkbox_options()
            lid=client.post('/listings',json=body).json()['id']
            response=client.post(f'/listings/{lid}/maintenance-references',json={
                'target_month':10,'household_size':1,'metering':'INDIVIDUAL','acknowledge_reference_limits':True})
            assert response.status_code==201,response.text
            saved=response.json()
        with server(path,url,clean,tmp_path) as client:
            client.headers['Authorization']='Bearer '+token
            assert client.get('/maintenance-references/'+saved['id']).json()==saved
            assert client.get(f'/listings/{lid}/report').json()['machine_maintenance_reference']==saved
    finally:
        if owner:store.delete_session(owner)
