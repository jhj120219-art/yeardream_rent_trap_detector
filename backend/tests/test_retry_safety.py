from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.db import Store, RequestConflict, InvalidReference
from backend.app.main import create_app
from backend.tests.test_backend import setup, payload, raw_rows
from backend.tests.test_mysql_persistence import target, server
from backend.scripts.import_data import import_raw


def test_api_retries_conflict_and_deleted_result(setup,monkeypatch):
    client,settings=setup
    headers={'Idempotency-Key':'listing-request-001'}
    first=client.post('/listings',json=payload(),headers=headers)
    assert first.status_code==201
    repeated=client.post('/listings',json=payload(),headers=headers)
    assert repeated.json()==first.json()
    assert len(client.get('/listings').json()['items'])==1
    assert client.post('/listings',json=payload(rent_10k_krw=81),headers=headers).status_code==409
    lid=first.json()['id']
    analysis_headers={'Idempotency-Key':'analysis-request-001'}
    a=client.post('/listings/'+lid+'/analyses',headers=analysis_headers)
    assert a.status_code==201
    # A replay must not run analysis again, even if current data is unavailable.
    import backend.app.analysis_service as service
    monkeypatch.setattr(service,'run',lambda *_:pytest.fail('analysis ran twice'))
    assert client.post('/listings/'+lid+'/analyses',headers=analysis_headers).json()==a.json()
    auth=client.headers['Authorization']
    with TestClient(create_app(settings)) as reopened:
        reopened.headers['Authorization']=auth
        assert reopened.post('/listings',json=payload(),headers=headers).json()==first.json()
    other=client.post('/sessions').json()['token']
    second=client.post('/listings',json=payload(),headers={**headers,'Authorization':'Bearer '+other})
    assert second.status_code==201 and second.json()['id']!=lid
    assert client.delete('/listings/'+lid).status_code==204
    assert client.post('/listings',json=payload(),headers=headers).status_code==409
    assert client.post('/listings/'+lid+'/analyses',headers=analysis_headers).status_code==409
    assert client.get('/listings').json()['items']==[]


def test_retry_key_optional_and_header_validation(setup):
    client,_=setup
    ids=[client.post('/listings',json=payload()).json()['id'] for _ in range(2)]
    assert ids[0]!=ids[1]
    for bad in ('short','contains spaces','x'*129):
        assert client.post('/listings',json=payload(),headers={'Idempotency-Key':bad}).status_code==422
    response=client.options('/listings',headers={'Origin':'http://localhost:5173',
        'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'Idempotency-Key'})
    assert response.status_code==200


def test_parallel_retries_are_atomic_on_real_storage(target):
    path,url=target
    store=Store(path,database_url=url)
    token=store.session();owner=store.owner(token)
    identity=('POST /listings','same-request-001','same-fingerprint')
    try:
        def create(_):return store.create(owner,'listing',{'input':payload()},request=identity)
        with ThreadPoolExecutor(max_workers=4) as workers:
            results=list(workers.map(create,range(4)))
        assert len({r['id'] for r in results})==1
        assert store.page(owner,'listing',20,0)['items']==[results[0]]
        # Reopening storage preserves the receipt without schema changes.
        reopened=Store(path,database_url=url,initialize=False)
        assert reopened.replay(owner,'listing',identity)==results[0]
        with pytest.raises(RequestConflict):
            store.create(owner,'listing',{},request=(identity[0],identity[1],'changed'))
        with pytest.raises(InvalidReference):
            store.create(owner,'listing',{},links={'previous_listing_id':'missing'},
                         request=('POST /listings','failed-request-001','fingerprint'))
        assert store.replay(owner,'listing',('POST /listings','failed-request-001','fingerprint')) is None
        store.delete(results[0]['id'],owner,'listing')
        with pytest.raises(RequestConflict):store.replay(owner,'listing',identity)
    finally:store.delete_session(owner)
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) AS total FROM objects WHERE owner=?',(owner,)).fetchone()['total']==0


def test_retry_receipt_survives_actual_http_process_restart(target,tmp_path):
    path,url=target
    raw=tmp_path/'raw.csv';clean=tmp_path/'clean.csv'
    raw_rows().to_csv(raw,index=False);import_raw(raw,clean)
    auth={}
    try:
        with server(path,url,clean,tmp_path) as client:
            auth={'Authorization':'Bearer '+client.post('/sessions').json()['token']}
            client.headers.update(auth)
            listing=client.post('/listings',json=payload(),headers={'Idempotency-Key':'restart-listing-001'}).json()
            route='/listings/'+listing['id']+'/analyses'
            analysis=client.post(route,headers={'Idempotency-Key':'restart-analysis-001'}).json()
            assert analysis['result']['status']=='COMPARED'
        with server(path,url,clean,tmp_path) as client:
            client.headers.update(auth)
            assert client.post('/listings',json=payload(),headers={'Idempotency-Key':'restart-listing-001'}).json()==listing
            assert client.post(route,headers={'Idempotency-Key':'restart-analysis-001'}).json()==analysis
            assert len(client.get('/listings').json()['items'])==1
    finally:
        if auth:
            store=Store(path,database_url=url,initialize=False)
            owner=store.owner(auth['Authorization'][7:])
            if owner:store.delete_session(owner)
