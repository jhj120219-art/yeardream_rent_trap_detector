import pytest
from backend.tests.test_backend import setup, payload


def evidence(**changes):
    body=dict(source_type='ADVERTISEMENT',source_title='통제 표본 광고',observed_on='2026-10-19',
              source_url='https://example.org/listing/1',amount_10k_krw=5,period='MONTH',
              applies_to='SAME_UNIT',user_confirmed=True,items={'WATER':'INCLUDED'})
    body.update(changes)
    return body


def submit(c, **changes):
    lid=c.post('/listings',json=payload()).json()['id']
    response=c.post(f'/listings/{lid}/maintenance-evidence',json=evidence(**changes))
    return lid,response


def test_difference_persist_owner_delete(setup):
    c,_=setup
    lid,r=submit(c)
    assert r.status_code==201,r.text
    obj=r.json(); oid=obj['id']
    assert obj['comparison']['difference_10k_krw']==2
    assert obj['comparison']['status']=='AMOUNT_DIFFERENCE'
    assert 'GAS' in obj['comparison']['unknown_items']
    assert c.get('/maintenance-evidence').json()['items'][0]==obj
    token=c.headers['Authorization']
    c.headers['Authorization']='Bearer '+c.post('/sessions').json()['token']
    assert c.get('/maintenance-evidence/'+oid).status_code==404
    assert c.post(f'/listings/{lid}/maintenance-evidence',json=evidence()).status_code==404
    c.headers['Authorization']=token
    assert c.delete('/listings/'+lid).status_code==204
    assert c.get('/maintenance-evidence/'+oid).status_code==404


@pytest.mark.parametrize('changes,reason',[
    ({'user_confirmed':False},'USER_CONFIRMATION_REQUIRED'),
    ({'period':'YEAR'},'MONTHLY_AMOUNT_REQUIRED'),
    ({'applies_to':'SAME_BUILDING'},'SAME_UNIT_NOT_CONFIRMED'),
    ({'amount_10k_krw':None},'AMOUNT_UNKNOWN'),
])
def test_hold(setup,changes,reason):
    _,r=submit(setup[0],**changes)
    result=r.json()['comparison']
    assert result['status']=='NEEDS_REVIEW'
    assert result['difference_10k_krw'] is None
    assert reason in result['reasons']


@pytest.mark.parametrize('changes',[{'amount_10k_krw':-1},{'user_confirmed':'true'},
    {'observed_on':'2099-01-01'},{'items':{'WATER':'YES'}},{'verified':True}])
def test_invalid(setup,changes):
    assert submit(setup[0],**changes)[1].status_code==422


def test_zero_and_explicit_delete(setup):
    c,_=setup
    body=payload(); body['options']['maintenance_10k_krw']=0
    lid=c.post('/listings',json=body).json()['id']
    r=c.post(f'/listings/{lid}/maintenance-evidence',json=evidence(amount_10k_krw=0))
    assert r.json()['comparison']['status']=='AMOUNT_MATCH'
    assert c.delete('/maintenance-evidence/'+r.json()['id']).status_code==204


def test_public_catalog_missing_invalid_and_loaded(setup,tmp_path,monkeypatch):
    import json
    import backend.app.maintenance as module
    path=tmp_path/'cases.json'
    monkeypatch.setattr(module,'CASES_PATH',path)
    c,_=setup
    assert c.get('/maintenance/reference-cases').status_code==503
    path.write_text('{}',encoding='utf-8')
    assert c.get('/maintenance/reference-cases').status_code==503
    path.write_text(json.dumps([{'case_id':'synthetic','evidence':evidence()}]),encoding='utf-8')
    assert c.get('/maintenance/reference-cases').json()['items'][0]['case_id']=='synthetic'


def test_unconfirmed_listing(setup):
    c,_=setup
    body=payload(); body['confirmation']['user_confirmed']=False
    lid=c.post('/listings',json=body).json()['id']
    r=c.post(f'/listings/{lid}/maintenance-evidence',json=evidence())
    assert r.json()['comparison']['difference_10k_krw'] is None
