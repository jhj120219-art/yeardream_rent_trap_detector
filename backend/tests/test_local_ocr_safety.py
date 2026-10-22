"""OCR boundary tests; mocked engine output is not an OCR accuracy evaluation."""
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import subprocess
import threading
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from backend.app import local_ocr
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.db import Store
from backend.tests.test_local_ocr import cards
from backend.tests.test_mysql_persistence import target
from backend.tests.test_backend import raw_rows
from backend.scripts.import_data import import_raw


def png():
    out=BytesIO();Image.new('RGB',(100,100),'white').save(out,format='PNG');return out.getvalue()


def test_partial_agreed_card_keeps_missing_null_and_explicit_zero():
    card=cards()[0]
    card['fields'].pop('area_m2')
    card['fields']['maintenance_10k_krw']={'value':0,'status':'extracted'}
    result=local_ocr.adapt_cards([card])
    assert result['extraction_status']=='EXTRACTED_NEEDS_REVIEW'
    assert result['fields']['area_m2']['value'] is None
    assert result['fields']['maintenance_10k_krw']['value']==0
    card['fields'].pop('maintenance_10k_krw')
    assert local_ocr.adapt_cards([card])['fields']['maintenance_10k_krw']['value'] is None


def test_partial_draft_persists_without_confirmation_and_other_owner_cannot_select(target,tmp_path,monkeypatch):
    path,url=target
    card=cards()[0];card['fields'].pop('maintenance_10k_krw');card['fields'].pop('area_m2')
    async def fake_read(*args):return local_ocr.adapt_cards([card,card])
    monkeypatch.setattr('backend.app.main.extract_local',fake_read)
    monkeypatch.setattr('backend.app.main.runtime_status',lambda _: {'state':'CONFIGURED','sites':['dabang']})
    source_csv=tmp_path/'raw.csv';clean=tmp_path/'clean.csv'
    raw_rows().to_csv(source_csv,index=False);import_raw(source_csv,clean)
    settings=Settings(db_path=path,database_url=url,clean_csv=clean,local_ocr_enabled=True)
    owners=[]
    try:
        with TestClient(create_app(settings)) as c:
            token=c.post('/sessions').json()['token'];c.headers['Authorization']='Bearer '+token
            owners.append(c.app.state.store.owner(token))
            source=c.post('/extractions',files={'file':('screen.png',png(),'image/png')}).json()
            selected=c.post('/extractions/'+source['id']+'/cards/0',headers={'Idempotency-Key':'selection-test-001'})
            assert selected.status_code==201,selected.text
            response=selected.json();body=response['draft']
            assert body['listing']['area_m2'] is None
            assert body['options']['maintenance_10k_krw'] is None
            assert body['listing']['rent_10k_krw']==60
            assert body['confirmation']['user_confirmed'] is False
            assert c.post('/extractions/'+source['id']+'/cards/0',headers={'Idempotency-Key':'selection-test-001'}).json()==response
            assert c.post('/extractions/'+source['id']+'/cards/1',headers={'Idempotency-Key':'selection-test-001'}).status_code==409
            listing=c.post('/listings',json=body)
            assert listing.status_code==201,listing.text
            lid=listing.json()['id']
            assert listing.json()['validation']['ok'] is False
            analysis=c.post('/listings/'+lid+'/analyses')
            assert analysis.status_code==201
            assert analysis.json()['result']['status']=='INPUT_REVIEW_REQUIRED'
            other=c.post('/sessions').json()['token'];owners.append(c.app.state.store.owner(other))
            c.headers['Authorization']='Bearer '+other
            assert c.post('/extractions/'+source['id']+'/cards/0').status_code==404
            assert c.get('/extractions/'+response['extraction_id']).status_code==404
        with TestClient(create_app(settings)) as reopened:
            reopened.headers['Authorization']='Bearer '+token
            assert reopened.get('/extractions/'+response['extraction_id']+'/listing-draft').json()['draft']==body
            assert reopened.get('/listings/'+lid).json()['input']['confirmation']['user_confirmed'] is False
    finally:
        store=Store(path,database_url=url,initialize=False)
        for owner in owners:store.delete_session(owner)


def test_flag_alone_does_not_claim_ocr_ready(tmp_path):
    settings=Settings(db_path=tmp_path/'db.sqlite3',database_url='',clean_csv=tmp_path/'missing.csv',
                      local_ocr_enabled=True,local_ocr_python=str(tmp_path/'missing-python.exe'))
    with TestClient(create_app(settings)) as c:
        cap=c.get('/capabilities').json()
        assert cap['vision_configured'] is False
        assert cap['local_ocr_runtime']=='UNAVAILABLE'
        c.headers['Authorization']='Bearer '+c.post('/sessions').json()['token']
        assert c.post('/extractions',files={'file':('x.png',png(),'image/png')}).status_code==503


def test_timeout_cleans_image_and_does_not_disclose_worker_error(monkeypatch):
    paths=[]
    def timeout(command,**kwargs):
        paths.append(Path(command[7]));assert paths[0].is_file()
        raise subprocess.TimeoutExpired(command,240,stderr='PRIVATE_DIAGNOSTICS')
    monkeypatch.setattr(local_ocr.subprocess,'run',timeout)
    with pytest.raises(HTTPException) as e:local_ocr._run(png(),'dabang')
    assert e.value.status_code==504
    assert 'PRIVATE_DIAGNOSTICS' not in e.value.detail
    assert not paths[0].parent.exists()


def test_busy_worker_is_not_queued(monkeypatch):
    entered=threading.Event();release=threading.Event()
    def wait(*args):entered.set();assert release.wait(5);return {}
    monkeypatch.setattr(local_ocr,'_run_locked',wait)
    thread=threading.Thread(target=lambda:local_ocr._run(png(),'dabang'));thread.start()
    try:
        assert entered.wait(3)
        with pytest.raises(HTTPException) as e:local_ocr._run(png(),'dabang')
        assert e.value.status_code==429
    finally:release.set();thread.join(5)


def test_worker_supports_main_reader_without_site_argument(tmp_path,monkeypatch):
    image=tmp_path/'x.png';image.write_bytes(png());output=tmp_path/'out.json'
    def legacy(path,engines,crop):
        assert crop==(0,0,100,100)
        assert engines==('easyocr',)
        return {'cards':[]}
    monkeypatch.setattr(local_ocr,'reader',lambda root:legacy)
    monkeypatch.setattr(local_ocr.sys,'argv',['worker','--engine','easyocr',str(image),str(output),'dabang',str(tmp_path)])
    assert local_ocr.worker()==0
    assert json.loads(output.read_text())=={'cards':[]}
    local_ocr.sys.argv[5]='zigbang'
    assert local_ocr.worker()==3
