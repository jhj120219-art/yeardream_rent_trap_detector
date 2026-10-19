from backend.tests.test_backend import setup, payload
from backend.tests.test_maintenance import evidence


def test_full_listing_flow_and_sections(setup):
    c,_=setup
    body=payload();body['options'].update(internet_status='INCLUDED',maintenance_10k_krw='7만원')
    saved=c.post('/listings',json=body).json();lid=saved['id']
    url=f'/listings/{lid}/report'
    first=c.get(url).json()
    assert first['rent']['state']=='NOT_ANALYZED'
    assert first['monthly_cost']['quoted_subtotal_10k_krw']==87
    assert first['maintenance']['state']=='NO_EVIDENCE'
    assert first['options']=={'internet_status':'INCLUDED'}
    assert 'RUN_RENT_ANALYSIS' in first['workflow']['next_actions']
    a=c.post(f'/listings/{lid}/analyses').json()
    assert c.post(f'/listings/{lid}/maintenance-evidence',json=evidence()).status_code==201
    final=c.get(url).json()
    assert final['rent']['result']==a['result']
    assert final['rent']['result']['rent_difference_10k_krw']==30
    assert final['rent']['comparable_transactions'] is None
    assert final['maintenance']['evidence']['total']==1
    assert final['maintenance']['evidence']['items'][0]['comparison']['difference_10k_krw']==2
    # 다른 매물의 근거 자료를 섞지 않는다.
    other=c.post('/listings',json=payload()).json()['id']
    assert c.get(f'/listings/{other}/report').json()['maintenance']['evidence']['total']==0
    page=c.get(url+'?evidence_offset=2').json()
    assert page['maintenance']['state']=='EVIDENCE_RECORDED'
    assert page['maintenance']['evidence']['items']==[]
    c.headers['Authorization']='Bearer '+c.post('/sessions').json()['token']
    assert c.get(url).status_code==404


def test_unconfirmed_unknown_cost_and_no_analysis_creation(setup):
    c,_=setup
    body=payload();body['confirmation']['user_confirmed']=False
    body['options']['maintenance_10k_krw']=None
    lid=c.post('/listings',json=body).json()['id']
    result=c.get(f'/listings/{lid}/report').json()
    assert result['monthly_cost']['quoted_subtotal_10k_krw'] is None
    assert result['rent']['state']=='NOT_ANALYZED'
    assert 'REVIEW_LISTING' in result['workflow']['next_actions']
    assert result['maintenance']['quoted_monthly_10k_krw'] is None


def test_zero_fee_latest_analysis_and_deletion(setup):
    c,_=setup
    body=payload();body['options']['maintenance_10k_krw']=0
    lid=c.post('/listings',json=body).json()['id']
    for _ in range(2):
        latest=c.post(f'/listings/{lid}/analyses').json()
    result=c.get(f'/listings/{lid}/report').json()
    assert result['rent']['analysis_id']==latest['id']
    assert result['monthly_cost']['quoted_subtotal_10k_krw']==80
    assert c.delete('/listings/'+lid).status_code==204
    assert c.get(f'/listings/{lid}/report').status_code==404
