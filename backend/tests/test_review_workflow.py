import json
import sqlite3
from fastapi.testclient import TestClient
import pytest
from backend.app.config import Settings
from backend.app.db import Store, InvalidReference
from backend.app.main import create_app
from backend.tests.test_backend import payload, png, setup


def extraction(client):
    # 세션별 보관 구조를 검증하는 모의 추출 초안. 실제 AI 호출/정확도 검증 아님.
    sid = client.app.state.store.owner(client.headers['Authorization'][7:])
    return client.app.state.store.create(sid,'extraction',{'result':{
        'extraction_status':'EXTRACTED_NEEDS_REVIEW',
        'fields':{'rent_10k_krw':{'value':50,'raw_text':'월세 50만원','review_required':True}},
    }})


def test_upload_endpoint_to_review_to_saved_analysis(setup):
    base,settings=setup
    async def fake_provider(data,config):
        assert data==png()
        return {'extraction_status':'EXTRACTED_NEEDS_REVIEW',
                'fields':{'rent_10k_krw':{'value':50,'raw_text':'월세50','review_required':True}}}
    with TestClient(create_app(settings,extractor=fake_provider)) as client:
        client.headers['Authorization']=base.headers['Authorization']
        source=client.post('/extractions',files={'file':('listing.png',png(),'image/png')})
        assert source.status_code==201
        body=payload(rent_10k_krw=80)
        body['source_extraction_id']=source.json()['id']
        body['confirmation']['input_source']='IMAGE_REVIEWED'
        saved=client.post('/listings',json=body)
        assert saved.status_code==201
        result=client.post('/listings/'+saved.json()['id']+'/analyses')
        assert result.status_code==201
        assert result.json()['result']['rent_difference_10k_krw']==30
        assert client.get('/listings').json()['items'][0]['links']['source_extraction_id']==source.json()['id']


def test_image_draft_review_revision_and_price_analysis(setup):
    client, settings = setup
    source = extraction(client)
    body = payload(rent_10k_krw=50)
    body.update(source_extraction_id=source['id'])
    body['confirmation'].update(input_source='IMAGE_REVIEWED',user_confirmed=False)
    draft = client.post('/listings',json=body).json()
    assert draft['confirmation_recorded_at'] is None
    result = client.post('/listings/'+draft['id']+'/analyses').json()['result']
    assert result['status']=='INPUT_REVIEW_REQUIRED'
    # 사용자가 추출 월세50을80으로 수정한 뒤 확인하고 새 스냅샷을 등록한다.
    body.pop('source_extraction_id')
    body['previous_listing_id']=draft['id']
    body['listing']['rent_10k_krw']=80
    body['confirmation']['user_confirmed']=True
    response=client.post('/listings',json=body)
    assert response.status_code==201, response.text
    saved=response.json()
    assert saved['links']=={'source_extraction_id':source['id'],'previous_listing_id':draft['id']}
    assert saved['confirmation_recorded_at']
    assert set(saved['input'])=={'schema_version','listing','options','confirmation'}
    assert client.get('/listings/'+draft['id']).json()['input']['listing']['rent_10k_krw']==50
    result=client.post('/listings/'+saved['id']+'/analyses').json()
    assert result['result']['status']=='COMPARED'
    assert result['result']['rent_difference_10k_krw']==30
    assert client.get('/analyses/'+result['id']).json()==result
    with TestClient(create_app(settings)) as reopened:
        assert reopened.get('/listings/'+saved['id'],headers={'Authorization':client.headers['Authorization']}).json()==saved


@pytest.mark.parametrize('relation',['source_extraction_id','previous_listing_id'])
def test_reference_cannot_access_other_users_objects(setup,relation):
    client,_=setup
    target=extraction(client) if relation=='source_extraction_id' else client.post('/listings',json=payload()).json()
    other=client.post('/sessions').json()['token']
    body=payload()
    body[relation]=target['id']
    body['confirmation']['input_source']='IMAGE_REVIEWED'
    response=client.post('/listings',json=body,headers={'Authorization':'Bearer '+other})
    assert response.status_code==404
    assert client.get('/listings',headers={'Authorization':'Bearer '+other}).json()['items']==[]


def test_source_kind_and_input_source_are_validated(setup):
    client,_=setup
    source=extraction(client)
    body=payload()
    body['source_extraction_id']=source['id']
    assert client.post('/listings',json=body).status_code==422
    body['confirmation']['input_source']='IMAGE_REVIEWED'
    listing=client.post('/listings',json=body).json()
    body['source_extraction_id']=listing['id']
    assert client.post('/listings',json=body).status_code==404
    body['source_extraction_id']='missing'
    assert client.post('/listings',json=body).status_code==404


def test_deleting_sources_does_not_erase_reviewed_snapshots(setup):
    client,_=setup
    source=extraction(client)
    body=payload()
    body['confirmation']['input_source']='IMAGE_REVIEWED'
    body['source_extraction_id']=source['id']
    original=client.post('/listings',json=body).json()
    body['previous_listing_id']=original['id']
    revised=client.post('/listings',json=body).json()
    analysis=client.post('/listings/'+revised['id']+'/analyses').json()
    assert client.delete('/extractions/'+source['id']).status_code==204
    obj=client.get('/listings/'+revised['id']).json()
    assert obj['links']['source_extraction_id'] is None
    assert obj['input']==revised['input']
    assert client.delete('/listings/'+original['id']).status_code==204
    assert client.get('/listings/'+revised['id']).json()['links']['previous_listing_id'] is None
    assert client.get('/analyses/'+analysis['id']).status_code==200
    assert client.delete('/listings/'+revised['id']).status_code==204
    assert client.get('/analyses/'+analysis['id']).status_code==404


def test_listing_history_pagination_is_private(setup):
    client,_=setup
    ids={client.post('/listings',json=payload()).json()['id'] for _ in range(3)}
    found=[]
    for offset in range(3):
        page=client.get('/listings',params={'limit':1,'offset':offset}).json()
        found.append(page['items'][0]['id'])
        assert page['has_more']==(offset<2)
    assert set(found)==ids and len(found)==len(set(found))
    assert client.get('/listings',params={'offset':3}).json()['items']==[]
    assert client.get('/listings',params={'limit':51}).status_code==422
    assert client.get('/listings',params={'offset':-1}).status_code==422
    other=client.post('/sessions').json()['token']
    assert client.get('/listings',headers={'Authorization':'Bearer '+other}).json()['items']==[]
    assert client.delete('/sessions/current').status_code==204
    assert client.get('/listings').status_code==401


def test_existing_database_gets_links_without_losing_records(tmp_path):
    path=tmp_path/'old.sqlite3'
    with sqlite3.connect(path) as db:
        db.executescript('''
        CREATE TABLE sessions(id TEXT PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE objects(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES sessions(id),kind TEXT NOT NULL,
        parent TEXT REFERENCES objects(id) ON DELETE CASCADE,payload TEXT NOT NULL,created_at TEXT NOT NULL);
        INSERT INTO sessions VALUES('owner','hash','2026-10-19');
        ''')
        db.execute('INSERT INTO objects VALUES(?,?,?,?,?,?)',('old','owner','listing',None,json.dumps({'input':payload()}),'2026-10-19'))
    store=Store(path)
    saved=store.get('old','owner','listing')
    assert saved['input']==payload()
    assert saved['links']=={'source_extraction_id':None,'previous_listing_id':None}
    with pytest.raises(InvalidReference):
        store.create('owner','listing',{'input':payload()},links={'source_extraction_id':'missing'})
    assert len(store.page('owner','listing',20,0)['items'])==1
