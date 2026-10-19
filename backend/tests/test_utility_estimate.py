import pytest
from backend.tests.test_backend import setup,payload
from backend.app.utility_estimate import electricity


def scenario(**changes):
    s=dict(scenario_month='2026-10',acknowledge_reference_limits=True,use_public_reference=True,
           electricity_contract='LOW_VOLTAGE',gas_supplier='SEOUL_CITY_GAS_SEOUL',household_size=1,
           water_individual_meter=True,water_meter_mm=15,internet_plan='KT_SLIM_100M_3Y')
    s.update(changes);return s


def submit(c,body=None,**changes):
    body=body or payload(building_type='MULTI_UNIT')
    for field in ['electricity_in_maintenance','gas_in_maintenance','water_in_maintenance','internet_status']:
        body['options'].setdefault(field,'SEPARATE_CHARGE')
    lid=c.post('/listings',json=body).json()['id']
    r=c.post(f'/listings/{lid}/utility-estimates',json=scenario(**changes))
    return lid,r


def test_public_references_calculation_storage_and_total(setup):
    c,settings=setup
    lid,r=submit(c)
    assert r.status_code==201,r.text
    obj=r.json();result=obj['result'];rows={x['item']:x for x in result['items']}
    assert rows['ELECTRICITY']['estimated_monthly_won']==41793
    assert rows['GAS']['estimated_monthly_won']==57786
    assert rows['WATER']['estimated_monthly_won']==10822
    assert rows['INTERNET']['estimated_monthly_won']==22000
    assert result['additional_utilities_won']==132401
    assert result['scenario_monthly_subtotal_won']==1002401
    assert rows['ELECTRICITY']['source']['area_specific'] is False
    assert c.get(f'/listings/{lid}/report').json()['utility_estimate']==obj
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
    with TestClient(create_app(settings)) as reopened:
        assert reopened.get('/utility-estimates/'+obj['id'],headers={'Authorization':c.headers['Authorization']}).json()==obj
    c.delete('/listings/'+lid)
    assert c.get('/utility-estimates/'+obj['id']).status_code==404


def test_included_no_double_count_unknown_not_zero(setup):
    body=payload();body['options'].update(internet_status='INCLUDED',water_in_maintenance='UNKNOWN')
    c,_=setup
    _,r=submit(c,body)
    rows={x['item']:x for x in r.json()['result']['items']}
    assert rows['INTERNET']['estimated_monthly_won'] is None
    assert rows['INTERNET']['additional_to_maintenance_won']==0
    assert rows['WATER']['estimated_monthly_won']==10822
    assert rows['WATER']['additional_to_maintenance_won'] is None
    assert r.json()['result']['scenario_monthly_subtotal_won'] is None


@pytest.mark.parametrize('changes,reason',[
    ({'electricity_contract':'UNKNOWN'},'LOW_VOLTAGE_CONTRACT_CONFIRMATION_REQUIRED'),
    ({'gas_supplier':'UNKNOWN'},'GAS_SUPPLIER_CONFIRMATION_REQUIRED'),
    ({'water_individual_meter':False},'INDIVIDUAL_15MM_METER_REQUIRED_NO_SHARED_ALLOCATION'),
])
def test_missing_conditions_block_totals(setup,changes,reason):
    _,r=submit(setup[0],**changes)
    result=r.json()['result']
    assert result['scenario_monthly_subtotal_won'] is None
    assert any(reason in row['reasons'] for row in result['items'])


@pytest.mark.parametrize('confirmed,ack',[(False,True),(True,False)])
def test_unreviewed_no_numbers(setup,confirmed,ack):
    body=payload();body['confirmation']['user_confirmed']=confirmed
    _,r=submit(setup[0],body,acknowledge_reference_limits=ack)
    assert r.json()['result']['state']=='NEEDS_REVIEW'
    assert all(x['estimated_monthly_won'] is None for x in r.json()['result']['items'])


def test_officetel_not_assigned_villa_average_and_direct_usage_allowed(setup):
    c,_=setup
    _,r=submit(c,payload(building_type='OFFICETEL'))
    assert r.json()['result']['items'][0]['state']=='NO_MATCHED_REFERENCE'
    _,r=submit(c,payload(building_type='OFFICETEL'),electricity_kwh=200,gas_mj=1000)
    assert r.json()['result']['items'][0]['source']['type']=='USER_SCENARIO_USAGE'
    assert r.json()['result']['state']=='ESTIMATED'


def test_other_region_and_owner_isolation(setup):
    c,_=setup
    lid,r=submit(c,payload(district_code='41110',legal_dong_code=None))
    assert r.json()['result']['scenario_monthly_subtotal_won'] is None
    # 기존 매물 계약의 지원지역 검증에서 이미 확인 필요인 입력은 견적도 보류한다.
    assert r.json()['result']['items'][0]['state']=='NEEDS_REVIEW'
    token=c.post('/sessions').json()['token']
    headers={'Authorization':'Bearer '+token}
    assert c.get('/utility-estimates/'+r.json()['id'],headers=headers).status_code==404
    assert c.post(f'/listings/{lid}/utility-estimates',json=scenario(),headers=headers).status_code==404


@pytest.mark.parametrize('changes',[{'electricity_kwh':-1},{'electricity_kwh':True},
    {'electricity_kwh':1001},{'household_size':True},{'household_size':0},
    {'scenario_month':'2027-01'},{'acknowledge_reference_limits':'true'},{'unknown_field':1}])
def test_invalid_scenarios(setup,changes):
    assert submit(setup[0],**changes)[1].status_code==422


def test_zero_usage_and_no_automatic_reference(setup):
    _,r=submit(setup[0],use_public_reference=False,electricity_kwh=0,gas_mj=0,water_m3=0)
    rows={x['item']:x for x in r.json()['result']['items']}
    assert rows['GAS']['estimated_monthly_won']==1375
    assert rows['WATER']['estimated_monthly_won']==1080
    _,r=submit(setup[0],use_public_reference=False)
    assert r.json()['result']['items'][0]['estimated_monthly_won'] is None


@pytest.mark.parametrize('kwh,base',[(0,910),(200,910),(200.1,1600),(400,1600),(400.1,7300)])
def test_progressive_base_boundaries(kwh,base):
    assert electricity(kwh)[1]['base_won']==base
