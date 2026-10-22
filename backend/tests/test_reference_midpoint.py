import os
from copy import deepcopy
import pytest
from backend.app.maintenance_selection import grouped_references
from backend.app.machine_reference import calculate, ReferenceScenario
from backend.tests.test_backend import payload
from backend.tests.test_maintenance_selection import checkbox_options


def test_midpoint_policy_keeps_bounds_missing_zero_and_half_won():
    refs={k:{'low_krw':1,'high_krw':2,'source':'SYNTHETIC_TEST'} for k in ('ELECTRICITY','WATER','GAS','INTERNET')}
    result=grouped_references(checkbox_options(),True,refs)
    assert result['representative_method']=='RANGE_MIDPOINT'
    assert result['selected']['items'][0]['reference_midpoint_krw']==1.5
    assert result['unselected']['reference_midpoint_total_krw']==3
    assert result['selected']['reference_midpoint_total_krw'] is None
    assert result['selected']['missing_items']==['OTHER']
    refs['OTHER']={'low_krw':0,'high_krw':0,'source':'SYNTHETIC_TEST'}
    assert grouped_references(checkbox_options(),True,refs)['selected']['reference_midpoint_total_krw']==3
    assert grouped_references(checkbox_options(),False,refs)['unselected']['reference_midpoint_total_krw'] is None


def test_real_analyst_fills_unchecked_without_changing_customer_selection():
    root=os.getenv('MAINTENANCE_INTEGRATION_ROOT')
    if not root:pytest.skip('Real analyst checkout required')
    body=payload();body['options']=checkbox_options();original=deepcopy(body)
    scenario=ReferenceScenario(target_month=10,household_size=1,heating_type='개별 도시가스',gas_user='예',metering='INDIVIDUAL',acknowledge_reference_limits=True)
    saved=calculate({'id':'SYNTHETIC_MIDPOINT_CHECK','input':body},scenario,root)
    rows={r['item']:r for g in ('selected','unselected') for r in saved['groups'][g]['items']}
    for key in ('WATER','ELECTRICITY','GAS','INTERNET'):
        row=rows[key]
        assert row['reference_state']=='AVAILABLE'
        assert row['reference_midpoint_krw']==(row['reference_low_krw']+row['reference_high_krw'])/2
    assert rows['ELECTRICITY']['selected'] is False and rows['GAS']['selected'] is False
    assert body==original
    assert saved['groups']['selected']['reference_midpoint_total_krw'] is None  # OTHER genuinely missing
    assert saved['groups']['unselected']['reference_midpoint_total_krw'] is not None
    # Analyst advertisement interpretation is preserved separately from all-item references.
    assert {r['utility_type'] for r in saved['result']['utility_estimates']}=={'WATER','INTERNET'}
    assert saved['reference_extension']['method']=='ANALYST_MONTH_REF_SAME_CONDITIONS'


def test_unknown_conditions_do_not_become_assumed_household_or_gas_heating():
    root=os.getenv('MAINTENANCE_INTEGRATION_ROOT')
    if not root:pytest.skip('Real analyst checkout required')
    body=payload();body['options']=checkbox_options()
    saved=calculate({'id':'SYNTHETIC_UNKNOWN_CHECK','input':body},ReferenceScenario(target_month=10,acknowledge_reference_limits=True),root)
    rows={r['item']:r for g in ('selected','unselected') for r in saved['groups'][g]['items']}
    assert rows['ELECTRICITY']['reference_state']=='AVAILABLE'
    assert rows['GAS']['reference_midpoint_krw'] is None
    assert rows['WATER']['reference_midpoint_krw'] is None
    assert saved['reference_extension']['conditions_used']['household_size'] is None
    assert saved['reference_extension']['conditions_used']['gas_user']=='모름'
