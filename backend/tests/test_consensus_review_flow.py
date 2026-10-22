from backend.tests.test_card_consensus import client, read


def body(row=None):
    row = row or read()
    return {'engine_reads': {'a': [row], 'b': [row]}, 'card_index': 0}


def test_agreed_card_stores_and_returns_unconfirmed_draft(client):
    saved = client.post('/extractions/card-consensus', json=body())
    assert saved.status_code == 201, saved.text
    source = saved.json()
    assert source['result']['source_type'] == 'ENGINE_CONSENSUS'
    assert source['result']['consensus_card']['user_confirmed'] is False
    draft = client.get('/extractions/' + source['id'] + '/listing-draft').json()
    assert draft['draft']['confirmation']['user_confirmed'] is False
    assert draft['draft']['source_extraction_id'] == source['id']
    assert draft['draft']['listing']['rent_10k_krw'] == 55
    assert draft['draft']['options']['maintenance_10k_krw'] == 10
    assert draft['draft']['listing']['area_basis'] is None
    assert draft['draft']['listing']['legal_dong_code'] is None
    assert draft['draft']['options']['water_in_maintenance'] is None
    assert client.get('/extractions/' + source['id']).json() == source
    assert client.delete('/extractions/' + source['id']).status_code == 204
    assert client.get('/extractions/' + source['id']).status_code == 404


def test_other_session_cannot_read_saved_card(client):
    source = client.post('/extractions/card-consensus', json=body()).json()
    client.headers['Authorization'] = 'Bearer ' + client.post('/sessions').json()['token']
    assert client.get('/extractions/' + source['id'] + '/listing-draft').status_code == 404
    assert client.delete('/extractions/' + source['id']).status_code == 404


def test_unagreed_card_and_invalid_index_are_rejected(client):
    data = body(); data['engine_reads']['b'] = []
    assert client.post('/extractions/card-consensus', json=data).status_code == 409
    data = body(); data['card_index'] = 100
    assert client.post('/extractions/card-consensus', json=data).status_code == 422
    data['card_index'] = True
    assert client.post('/extractions/card-consensus', json=data).status_code == 422


def test_jeonse_not_registered_as_rent(client):
    assert client.post('/extractions/card-consensus', json=body(read(kind='전세', rent=None))).status_code == 422


def test_oversized_engine_reads_are_not_silently_truncated(client):
    data = {'engine_reads': {'a': [read()] * 301, 'b': [read()]}}
    assert client.post('/extraction/card-consensus', json=data).status_code == 422
    data['engine_reads']['a'].pop()
    assert client.post('/extraction/card-consensus', json=data).status_code == 200
    data['engine_reads']['   '] = []
    assert client.post('/extraction/card-consensus', json=data).status_code == 422


def test_saved_consensus_requires_session(client):
    client.headers.pop('Authorization')
    assert client.post('/extractions/card-consensus', json=body()).status_code in (401, 403)
