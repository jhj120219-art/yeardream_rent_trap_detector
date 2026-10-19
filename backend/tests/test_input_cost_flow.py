from backend.tests.test_backend import setup,payload
from backend.tests.test_review_workflow import extraction
from backend.app.cost_items import cost_items


def test_draft_to_reviewed_registration_to_report(setup):
    c,_=setup
    source=extraction(c)
    draft=c.get('/extractions/'+source['id']+'/listing-draft').json()
    body=draft['draft']
    assert body['confirmation']['user_confirmed'] is False
    assert body['listing']['rent_10k_krw']==50
    assert body['listing']['legal_dong_code'] is None
    assert body['listing']['unit_ho'] is None
    body['listing'].update(payload()['listing'])
    body['options'].update(maintenance_10k_krw=7,internet_status='INCLUDED',gas_in_maintenance='SEPARATE_CHARGE')
    body['confirmation'].update(user_confirmed=True,confirmed_fields=['floor'])
    saved=c.post('/listings',json=body)
    assert saved.status_code==201,saved.text
    lid=saved.json()['id']
    assert c.post(f'/listings/{lid}/analyses').status_code==201
    report=c.get(f'/listings/{lid}/report').json()
    costs={x['item']:x for x in report['utility_costs']['items']}
    assert costs['INTERNET']['additional_to_maintenance_10k_krw']==0
    assert costs['GAS']['additional_to_maintenance_10k_krw'] is None
    assert report['monthly_cost']['quoted_subtotal_10k_krw']==87
    assert report['property']['links']['source_extraction_id']==source['id']
    c.headers['Authorization']='Bearer '+c.post('/sessions').json()['token']
    assert c.get('/extractions/'+source['id']+'/listing-draft').status_code==404


def test_multiple_listings_do_not_prefill(setup):
    c,_=setup
    sid=c.app.state.store.owner(c.headers['Authorization'][7:])
    source=c.app.state.store.create(sid,'extraction',{'result':{
        'extraction_status':'MULTIPLE_LISTINGS',
        'fields':{'rent_10k_krw':{'value':50,'raw_text':'50'}}}})
    draft=c.get('/extractions/'+source['id']+'/listing-draft').json()['draft']
    assert draft['listing']['rent_10k_krw'] is None
    assert draft['confirmation']['user_confirmed'] is False


def test_available_is_not_included_and_unconfirmed_is_not_free():
    for confirmed in (True,False):
        items=cost_items({'internet_status':'AVAILABLE','gas_in_maintenance':'INCLUDED'},confirmed)['items']
        rows={x['item']:x for x in items}
        assert rows['INTERNET']['advertised_status']=='UNKNOWN'
        assert rows['INTERNET']['additional_to_maintenance_10k_krw'] is None
        assert rows['GAS']['additional_to_maintenance_10k_krw']==(0 if confirmed else None)
        assert all(x['reference_monthly_10k_krw'] is None for x in items)
