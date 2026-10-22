from copy import deepcopy
import pytest
from backend.app.rent_presentation import rent_presentation
from backend.tests.test_backend import setup, payload


def analysis(diff=10, ratio=1/6, status='COMPARED', stage=1):
    return {'status':status, 'price_label':'UPPER_RANGE', 'stage':stage,
            'prices_10k_krw':{'median':60,'q25':55,'q75':65},
            'rent_difference_10k_krw':diff,'rent_difference_pct':ratio,
            'reference':{'conditions':{'scope_code':'DISTRICT' if stage==3 else 'LEGAL_DONG'}}}


@pytest.mark.parametrize('diff,ratio,tone,direction,word',[
    (10,1/6,'RED','HIGHER','높아요'),(-10,-1/6,'BLUE','LOWER','낮아요'),(0,0,'NEUTRAL','SAME','같아요')])
def test_difference_and_percentage_are_source_values_with_accessible_direction(diff,ratio,tone,direction,word):
    result=analysis(diff,ratio);original=deepcopy(result)
    p=rent_presentation(result,60+diff,True,True)
    assert p['tone']==tone and p['direction']==direction and word in p['headline']
    assert p['difference_10k_krw']==diff
    assert p['difference_percent']==pytest.approx(ratio*100)
    assert p['reference_rent_10k_krw']==60 and p['percent_basis']=='COMPARABLE_MEDIAN'
    assert result==original


@pytest.mark.parametrize('status,stage',[('REFERENCE_ONLY',1),('COMPARED',3)])
def test_reference_only_or_district_scope_cannot_show_colored_verdict(status,stage):
    source=analysis(status=status,stage=stage)
    p=rent_presentation(source,70,True,True)
    assert p['state']=='REFERENCE_ONLY' and p['tone']=='NEUTRAL'
    assert p['can_show_direction'] is False and p['direction'] is None
    assert p['difference_percent']==pytest.approx(100/6)
    assert source['status']==status


@pytest.mark.parametrize('status',['INSUFFICIENT_DATA','INPUT_REVIEW_REQUIRED','OUT_OF_SCOPE'])
def test_unusable_result_never_leaks_stale_numeric_comparison(status):
    p=rent_presentation(analysis(status=status),70,True,True)
    assert p['difference_10k_krw'] is None and p['reference_rent_10k_krw'] is None
    assert p['tone']=='NEUTRAL' and p['can_show_direction'] is False


@pytest.mark.parametrize('field,value',[('rent_difference_pct',None),('rent_difference_pct',True),
    ('rent_difference_pct',float('nan')),('rent_difference_10k_krw',None)])
def test_missing_or_invalid_source_is_not_replaced_by_zero(field,value):
    r=analysis();r[field]=value
    p=rent_presentation(r,70,True,True)
    assert p['difference_percent'] is None and not p['can_show_direction']
    assert 'DISPLAY_DATA_INCOMPLETE' in p['reason_codes']


def test_unconfirmed_unknown_and_conflicting_source_have_safe_display():
    assert rent_presentation(analysis(),70,False,True)['reference_rent_10k_krw'] is None
    assert rent_presentation(None,70,True,True)['state']=='NOT_ANALYZED'
    p=rent_presentation(analysis(10,-0.1),70,True,True)
    assert p['tone']=='NEUTRAL' and not p['can_show_direction']
    assert 'DISPLAY_DATA_INCONSISTENT' in p['reason_codes']


def test_report_exposes_display_without_changing_analysis_or_using_management_fee(setup):
    c,_=setup
    results=[]
    for fee in [0,999]:
        body=payload();body['options']['maintenance_10k_krw']=fee
        lid=c.post('/listings',json=body).json()['id']
        raw=c.post('/listings/'+lid+'/analyses').json()
        report=c.get('/listings/'+lid+'/report').json()
        assert report['rent']['result']==raw['result']
        assert report['rent']['presentation']['difference_10k_krw']==30
        assert report['rent']['presentation']['difference_percent']==60
        results.append(report['rent']['presentation'])
    assert results[0]==results[1]
