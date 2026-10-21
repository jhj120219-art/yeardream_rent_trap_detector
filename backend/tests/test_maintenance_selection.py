import pytest
from backend.app.maintenance_selection import grouped_references
from backend.app.advertised_costs import ITEMS
from backend.tests.test_backend import payload, setup
from backend.tests.test_mysql_persistence import target
from backend.app.db import Store


def checkbox_options():
    o = {'maintenance_input_mode': 'CHECKBOX_TOTAL_V1', 'maintenance_10k_krw': 7}
    for item, (field, _) in ITEMS.items():
        o[field] = 'INCLUDED' if item in ('WATER', 'INTERNET', 'OTHER') else 'UNKNOWN'
    return o


def test_unconnected_groups_preserve_unknown_and_never_split_total():
    result = grouped_references(checkbox_options(), True)
    assert [r['item'] for r in result['selected']['items']] == ['WATER', 'INTERNET', 'OTHER']
    assert [r['item'] for r in result['unselected']['items']] == ['ELECTRICITY', 'GAS']
    assert result['selected']['missing_items'] == ['WATER', 'INTERNET', 'OTHER']
    assert result['selected']['reference_low_total_krw'] is None
    assert result['advertised_selected_total_10k_krw'] == 7
    assert all(r['reference_low_krw'] is None for r in result['selected']['items'])


def test_partial_reference_does_not_invent_other_or_complete_subtotal():
    # Synthetic values test grouping and arithmetic only, not production evidence.
    refs = {k: {'low_krw': 10000, 'high_krw': 20000, 'source': 'TEST_ONLY'} for k in ITEMS if k != 'OTHER'}
    result = grouped_references(checkbox_options(), True, refs)
    assert result['selected']['reference_low_total_krw'] is None
    assert result['selected']['missing_items'] == ['OTHER']
    assert result['unselected']['reference_low_total_krw'] == 20000
    refs['OTHER'] = {'low_krw': 0, 'high_krw': 0, 'source': 'TEST_ONLY'}
    result = grouped_references(checkbox_options(), True, refs)
    assert result['selected']['reference_low_total_krw'] == 20000
    unconfirmed = grouped_references(checkbox_options(), False, refs)
    assert unconfirmed['selected']['reference_low_total_krw'] is None
    assert unconfirmed['state'] == 'NEEDS_USER_CONFIRMATION'


@pytest.mark.parametrize('low,high,source', [(True, 20, 'x'), (-1, 20, 'x'),
    (20, 10, 'x'), ('NaN', 20, 'x'), (1.5, 2, 'x'), (0, 0, None)])
def test_invalid_or_unsourced_reference_is_not_displayed(low, high, source):
    r = grouped_references(checkbox_options(), True,
            {'WATER': {'low_krw': low, 'high_krw': high, 'source': source}})
    assert r['selected']['items'][0]['reference_state'] == 'NO_REFERENCE'


def test_checkbox_total_api_contract_and_owner_isolation(setup):
    c, _ = setup
    body = payload(); body['options'] = checkbox_options()
    response = c.post('/listings', json=body)
    assert response.status_code == 201
    lid = response.json()['id']
    report = c.get('/listings/'+lid+'/report').json()
    assert report['maintenance_reference_groups']['selected']['missing_items'] == ['WATER', 'INTERNET', 'OTHER']
    assert report['advertised_costs']['maintenance_10k_krw'] == 7
    assert report['advertised_costs']['items'][0]['status'] == 'UNKNOWN'
    body['options']['water_10k_krw'] = 1
    assert c.post('/listings', json=body).status_code == 422
    body['options'].pop('water_10k_krw')
    body['options'].pop('water_in_maintenance')
    assert c.post('/listings', json=body).status_code == 422
    c.headers['Authorization'] = 'Bearer '+c.post('/sessions').json()['token']
    assert c.get('/listings/'+lid+'/report').status_code == 404


def test_selection_survives_database_reopen_without_item_amounts(target):
    path,url=target
    store=Store(path,database_url=url);owner=store.owner(store.session())
    try:
        raw=payload();raw['options']=checkbox_options()
        obj=store.create(owner,'listing',{'input':raw})
        reopened=Store(path,database_url=url,initialize=False)
        assert reopened.get(obj['id'],owner,'listing')['input']['options']==checkbox_options()
        saved=reopened.maintenance(obj['id'],owner)
        assert len(saved['items'])==5
        assert all(r['quoted_monthly_10k_krw'] is None for r in saved['items'])
    finally:
        store.delete_session(owner)
