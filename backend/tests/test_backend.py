"""실거래 원본 없이도 재현 가능한 통제 표본. 운영 데이터/정확도 검증으로 사용하지 않는다."""
import copy
import os
from io import BytesIO
import json
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from PIL import Image
import compare_rent
from backend.app.config import Settings, ROOT, ANALYSIS_ROOT
from backend.app.main import create_app
from backend.app.vision import image_url, validate_output, TEMPLATE, extract_image
from backend.scripts.import_data import import_raw


def raw_rows(n=40):
    return pd.DataFrame([dict(CGG_CD='11620',STDG_CD='10100',CGG_NM='관악구',STDG_NM='봉천동',BLDG_USG='아파트',RENT_AREA='59.9',GRFE='5000',RTFE=str(48+i%5),ARCH_YR='2005',FLR='5',CTRT_DAY=f'202609{1+i%20:02d}',NEW_UPDT_YN='신규',RENT_SE='월세',MNO='1',SNO='0',BLDG_NM='테스트 건물') for i in range(n)])


def payload(**changes):
    data={'schema_version':'1.1','listing':dict(district_code='11620',legal_dong_code='1162010100',building_type='APARTMENT',area_m2=59.9,area_basis='EXCLUSIVE',deposit_10k_krw=5000,rent_10k_krw=80,built_year=2005,floor=5,floor_type='GROUND',floor_source='USER_CONFIRMED',as_of='2026-10-01',address_text='테스트 주소',unit_ho='501'), 'options':{'maintenance_10k_krw':7},'confirmation':{'user_confirmed':True,'input_source':'ADDRESS_MANUAL','confirmed_fields':['floor']}}
    data['listing'].update(changes)
    return data


@pytest.fixture
def setup(tmp_path):
    source=tmp_path/'raw.csv'
    raw_rows().to_csv(source,index=False)
    clean=tmp_path/'clean.csv'
    import_raw(source,clean)
    settings=Settings(db_path=tmp_path/'db.sqlite3',clean_csv=clean)
    with TestClient(create_app(settings)) as client:
        token=client.post('/sessions').json()['token']
        client.headers['Authorization']='Bearer '+token
        yield client,settings


def submit(client, data):
    saved=client.post('/listings',json=data)
    assert saved.status_code==201,saved.text
    result=client.post('/listings/'+saved.json()['id']+'/analyses')
    return saved.json(),result


def test_price_contract_and_persistence(setup):
    c,s=setup
    saved,result=submit(c,payload())
    assert result.status_code==201,result.text
    r=result.json()['result']
    assert (r['status'],r['price_label'],r['sample_count'])==('COMPARED','UPPER_TAIL',40)
    assert r['options']['maintenance_10k_krw']==7
    assert r['rent_difference_10k_krw']==30
    assert saved['input']['listing']['unit_ho']=='501'
    token=c.headers['Authorization']
    with TestClient(create_app(s)) as reopened:
        assert reopened.get('/analyses/'+result.json()['id'],headers={'Authorization':token}).json()==result.json()


def test_confirmation_blocks_analysis(setup):
    c,_=setup
    body=payload()
    body['confirmation']['user_confirmed']=False
    _,result=submit(c,body)
    assert result.json()['result']['status']=='INPUT_REVIEW_REQUIRED'
    assert 'USER_CONFIRMATION_REQUIRED' in result.json()['result']['input_issues']


@pytest.mark.parametrize('basis',['SUPPLY','CONTRACT'])
def test_area_policy_unchanged(setup,basis):
    _,r=submit(setup[0],payload(area_basis=basis))
    assert r.json()['result']['status']=='REFERENCE_ONLY'
    assert r.json()['result']['price_label']=='UNRATED'


def test_empty_comparables(setup):
    _,r=submit(setup[0],payload(building_type='OFFICETEL'))
    assert r.json()['result']['status']=='INSUFFICIENT_DATA'


def test_out_of_scope(setup):
    _,r=submit(setup[0],payload(district_code='11110',legal_dong_code=None,dong='사직동'))
    assert r.json()['result']['status']=='OUT_OF_SCOPE'


def test_image_floor_not_trusted(setup):
    body=payload(building_type='DETACHED_MULTI',floor_source='IMAGE_EXTRACTED')
    body['confirmation'].update(input_source='IMAGE_REVIEWED',confirmed_fields=[])
    saved,_=submit(setup[0],body)
    assert saved['validation']['floor_final']['floor_type']=='UNKNOWN'
    assert saved['validation']['floor_final']['floor'] is None


def test_owner_isolation_and_cascade(setup):
    c,_=setup
    saved,result=submit(c,payload())
    other=c.post('/sessions').json()['token']
    auth={'Authorization':'Bearer '+other}
    assert c.get('/listings/'+saved['id'],headers=auth).status_code==404
    assert c.get('/analyses/'+result.json()['id'],headers=auth).status_code==404
    assert c.delete('/listings/'+saved['id'],headers=auth).status_code==404
    assert c.delete('/listings/'+saved['id']).status_code==204
    assert c.get('/analyses/'+result.json()['id']).status_code==404


def test_delete_session(setup):
    c,_=setup
    saved,_=submit(c,payload())
    assert c.delete('/sessions/current').status_code==204
    assert c.get('/listings/'+saved['id']).status_code==401


@pytest.mark.parametrize('change',[{'as_of':'nonsense'},{'area_m2':'NaN'},{'built_year':'Infinity'},{'rent_10k_krw':{'value':50}},{'floor':[1,2]}])
def test_invalid_http_input(setup,change):
    assert setup[0].post('/listings',json=payload(**change)).status_code==422


def test_strict_confirmation(setup):
    body=payload()
    body['confirmation']['user_confirmed']='true'
    assert setup[0].post('/listings',json=body).status_code==422


def test_auth_required(setup):
    assert setup[0].post('/listings',json=payload(),headers={'Authorization':''}).status_code==401


def test_missing_data_not_faked(tmp_path):
    with TestClient(create_app(Settings(db_path=tmp_path/'db',clean_csv=tmp_path/'missing'))) as c:
        c.headers['Authorization']='Bearer '+c.post('/sessions').json()['token']
        assert c.get('/health').json()['data_status']=='MISSING'
        assert c.get('/ready').status_code==503
        saved=c.post('/listings',json=payload()).json()
        assert c.post('/listings/'+saved['id']+'/analyses').status_code==503


def test_invalid_dataset_does_not_crash(tmp_path):
    bad=tmp_path/'bad.csv';bad.write_text('x\n1\n')
    with TestClient(create_app(Settings(db_path=tmp_path/'db',clean_csv=bad))) as c:
        assert c.get('/health').json()['data_status']=='INVALID'


def test_import_idempotency_and_preserves_identical_contracts(tmp_path):
    src=tmp_path/'raw.csv';out=tmp_path/'clean.csv'
    df=raw_rows(3)
    pd.concat([df,df.iloc[[0]]]).to_csv(src,index=False)
    first=import_raw(src,out)
    assert first['rows']==4
    assert import_raw(src,out)['sha256']==first['sha256']
    df.loc[0,'RTFE']='70';df.to_csv(src,index=False)
    import_raw(src,out)
    assert len(pd.read_csv(out))==3
    assert pd.read_csv(out).iloc[0]['rent']==70
    before=out.read_bytes()
    src.write_text('bad\nvalue\n')
    with pytest.raises(KeyError):
        import_raw(src,out)
    assert out.read_bytes()==before


def png():
    b=BytesIO();Image.new('RGB',(10,10)).save(b,format='PNG');return b.getvalue()


def test_invalid_image_and_unconfigured_provider(setup):
    c,_=setup
    assert c.post('/extractions',files={'file':('x.png',b'notimage','image/png')}).status_code==422
    assert c.post('/extractions',files={'file':('x.png',png(),'image/png')}).status_code==503


def test_image_result_sanitization():
    data=copy.deepcopy(TEMPLATE)
    data['fields']['built_year']={'value':2000,'raw_text':None,'review_required':False}
    data['fields']['floor']['raw_text']='4층 건물'
    data['fields']['floor_type']['raw_text']='4층 건물'
    r=validate_output(data)
    assert r['fields']['built_year']['value'] is None
    assert r['fields']['floor']['value'] is None
    assert r['fields']['total_floors']['value']==4
    assert all(x['review_required'] for x in r['fields'].values())


def test_multiple_listings_clear_values():
    data=copy.deepcopy(TEMPLATE);data['extraction_status']='MULTIPLE_LISTINGS'
    data['fields']['floor']['raw_text']='4층 중 3층'
    result=validate_output(data)
    assert result['fields']['rent_10k_krw']['value'] is None
    # 여러 매물일 때 층 문구로 단일 매물 층을 되살리지 않아야 한다.
    assert result['fields']['floor']['value'] is None


def test_extraction_flow_with_injected_provider(tmp_path):
    async def fake(data,settings):
        return validate_output(copy.deepcopy(TEMPLATE))
    with TestClient(create_app(Settings(db_path=tmp_path/'db',clean_csv=tmp_path/'missing'),extractor=fake)) as c:
        c.headers['Authorization']='Bearer '+c.post('/sessions').json()['token']
        response=c.post('/extractions',files={'file':('image.png',png(),'image/png')})
        assert response.status_code==201
        oid=response.json()['id']
        assert c.get('/extractions/'+oid).json()==response.json()
        assert c.delete('/extractions/'+oid).status_code==204
        assert c.get('/extractions/'+oid).status_code==404


def test_provider_wire_format_and_failures(monkeypatch,tmp_path):
    import asyncio
    import httpx
    import backend.app.vision as vision
    calls=[]
    class Client:
        def __init__(self,**kwargs): pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,headers,json):
            calls.append(json)
            return httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'finish_reason':'stop','message':{'content':__import__('json').dumps(TEMPLATE)}}]})
    monkeypatch.setattr(vision.httpx,'AsyncClient',Client)
    settings=Settings(db_path=tmp_path/'db',openai_key='test-only',vision_model='test-only')
    result=asyncio.run(extract_image(png(),settings))
    assert result['extraction_status']=='EXTRACTED_NEEDS_REVIEW'
    assert calls[0]['response_format']['json_schema']['strict'] is True
    assert calls[0]['messages'][1]['content'][0]['image_url']['url'].startswith('data:image/jpeg;base64,')


@pytest.mark.parametrize('value',['1e999','-NaN','-Infinity'])
def test_nonfinite_text_rejected(setup,value):
    assert setup[0].post('/listings',json=payload(built_year=value)).status_code==422


def test_unbounded_date_rejected(setup):
    assert setup[0].post('/listings',json=payload(as_of='0001-01-01')).status_code==422


def test_address_unconfigured(setup):
    assert setup[0].get('/addresses/search',params={'q':'관악구 봉천동'}).status_code==503


def test_address_legal_code_mapping(monkeypatch,tmp_path):
    import asyncio
    import httpx
    import backend.app.address as address
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,url,params,headers):
            return httpx.Response(200,request=httpx.Request('GET',url),json={'documents':[{'address':{'address_name':'테스트 주소','b_code':'1162010100','h_code':'1162052500','region_3depth_name':'봉천동'},'road_address':None}]})
    monkeypatch.setattr(address.httpx,'AsyncClient',Client)
    result=asyncio.run(address.search_address('테스트',Settings(kakao_key='test-only')))
    assert result['candidates'][0]['legal_dong_code']=='1162010100'
    assert result['candidates'][0]['district_code']=='11620'


def test_large_body_rejected(setup):
    assert setup[0].post('/listings',content=b'x'*(9*1024*1024+1)).status_code==413


def test_team_normalize_regressions_in_isolation(tmp_path):
    # 기존 스크립트가 output CSV를 쓰므로 임시 복사본에서 실행한다.
    import shutil
    import subprocess
    import sys
    for name in ('test_normalize.py','normalize_listing.py','analyze.py','compare_rent.py'):
        shutil.copy2(ANALYSIS_ROOT/name,tmp_path/name)
    (tmp_path/'output').mkdir()
    proc=subprocess.run([sys.executable,'test_normalize.py'],cwd=tmp_path,capture_output=True,text=True,
                        encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    assert proc.returncode==0,proc.stderr
    results=pd.read_csv(tmp_path/'output/test_normalize_results.csv')
    assert len(results)==38
    assert (results['통과']=='PASS').all(),results[results['통과']!='PASS'].to_string()
