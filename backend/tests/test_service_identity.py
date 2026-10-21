from backend.app.service_identity import public_identity
from backend.tests.test_backend import setup, payload


def test_public_identity_is_consistent_in_capabilities_report_and_openapi(setup):
    c, _ = setup
    identity = c.get('/capabilities').json()['service']
    assert identity['name'] == '월세구멍'
    assert identity['slogan'] == '마음에 든 집, 놓친 건 없을까?'
    assert identity['maintenance_policy'] == 'FIVE_ITEMS_ALL_HOUSING_TYPES'
    assert [r['item'] for r in identity['maintenance_display_items']] == ['WATER','ELECTRICITY','GAS','INTERNET','OTHER']
    assert c.get('/openapi.json').json()['info']['title'] == '월세구멍 API'
    lid = c.post('/listings', json=payload()).json()['id']
    assert c.get('/listings/'+lid+'/report').json()['service'] == identity
    # A caller cannot mutate the server's shared metadata through a returned object.
    identity['maintenance_display_items'].clear()
    assert len(public_identity()['maintenance_display_items']) == 5
