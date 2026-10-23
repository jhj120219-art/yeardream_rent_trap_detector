from backend.app.local_ocr import adapt_cards, choose_card
from fastapi import HTTPException
from machine.analysis_internal.extraction.consensus import consensus
import pytest

def cards(kind='월세'):
    values=[(kind,1000,60 if kind=='월세' else None,20.8,7)]
    return consensus({'easyocr':values,'paddle':values})

def test_single_agreed_monthly_is_unconfirmed_draft():
    result=adapt_cards(cards())
    assert result['extraction_status']=='EXTRACTED_NEEDS_REVIEW'
    assert result['fields']['area_m2']['value']==20.8
    assert result['fields']['area_m2']['review_required'] is True
    assert 'area_basis' not in result['fields']
    assert 'water_in_maintenance' not in result['fields']

def test_multiple_requires_selection_and_does_not_merge_values():
    values=[('월세',1000,60,20.8,7),('월세',2000,80,30,10)]
    result=adapt_cards(consensus({'a':values,'b':values}))
    assert result['extraction_status']=='MULTIPLE_LISTINGS'
    assert result['fields']=={}
    selected=choose_card(result,1)
    assert selected['fields']['deposit_10k_krw']['value']==2000

def test_held_jeonse_and_invalid_index_never_autofill():
    for result in (adapt_cards(cards('전세')),adapt_cards(consensus({'a':[('월세',1000,60,20.8,7)]}))):
        assert result['extraction_status']!='EXTRACTED_NEEDS_REVIEW'
        with pytest.raises(HTTPException):choose_card(result,0)
    with pytest.raises(HTTPException):choose_card(adapt_cards(cards()),-1)

def test_empty_image_has_no_listing():
    assert adapt_cards([])['extraction_status']=='NO_LISTING_FOUND'

def test_http_card_selection_is_owner_scoped_and_review_required(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
    from backend.app.config import Settings
    import backend.app.main as main
    values=[('월세',1000,60,20.8,7),('월세',2000,80,30,10)]
    async def fake_read(data, settings, site):
        assert site=='zigbang'
        return adapt_cards(consensus({'a':values,'b':values}))
    monkeypatch.setattr(main,'extract_local',fake_read)
    monkeypatch.setattr(main,'runtime_status',lambda settings: {'state':'CONFIGURED','sites':['dabang','zigbang']})
    settings=Settings(db_path=tmp_path/'test.sqlite3',database_url='',clean_csv=tmp_path/'none.csv',local_ocr_enabled=True)
    with TestClient(create_app(settings)) as c:
        token=c.post('/sessions').json()['token'];c.headers['Authorization']='Bearer '+token
        assert c.get('/capabilities').json()['image_provider']=='LOCAL_OCR'
        saved=c.post('/extractions',files={'file':('listing.png',b'image','image/png')},data={'site':'zigbang'})
        assert saved.status_code==201
        eid=saved.json()['id']
        draft=c.get(f'/extractions/{eid}/listing-draft').json()
        assert draft['extraction_status']=='MULTIPLE_LISTINGS'
        assert len(draft['ocr_cards'])==2
        chosen=c.post(f'/extractions/{eid}/cards/1')
        assert chosen.status_code==201
        assert chosen.json()['draft']['listing']['rent_10k_krw']==80
        assert chosen.json()['draft']['confirmation']['user_confirmed'] is False
        assert c.post(f'/extractions/{eid}/cards/-1').status_code==422
        c.headers['Authorization']='Bearer '+c.post('/sessions').json()['token']
        assert c.post(f'/extractions/{eid}/cards/1').status_code==404

def test_bad_image_is_rejected_before_worker():
    from backend.app.local_ocr import _run
    with pytest.raises(HTTPException) as e:
        _run(b'not image','dabang')
    assert e.value.status_code==422


# ---- 부분 입력: 인식된 항목만 입력 ----
def test_partial_card_fills_only_agreed_fields_and_leaves_rest_empty():
    # 두 엔진이 머리줄·면적은 같게 읽고 관리비는 서로 다르게 읽음 → 관리비만 비움
    result = adapt_cards(consensus({'easyocr': [('월세', 1000, 55, 20.8, 7)], 'paddle': [('월세', 1000, 55, 20.8, 5)]}))
    assert result['extraction_status'] == 'EXTRACTED_NEEDS_REVIEW'
    f = result['fields']
    assert f['area_m2']['value'] == 20.8 and f['rent_10k_krw']['value'] == 55
    assert f['maintenance_10k_krw']['value'] is None and f['maintenance_10k_krw']['raw_text'] is None


def test_card_without_maintenance_is_still_entered():
    v = [('월세', 1000, 55, 20.8, None)]
    result = adapt_cards(consensus({'a': v, 'b': v}))
    assert result['extraction_status'] == 'EXTRACTED_NEEDS_REVIEW'
    assert result['fields']['maintenance_10k_krw']['value'] is None and result['fields']['deposit_10k_krw']['value'] == 1000


def test_address_only_photo_enters_only_the_address():
    imf = {'address_text': {'value': '서울 마포구 합정동 10-2', 'status': 'agreed', 'autofill': True},
           'area_m2': {'value': None, 'status': 'missing', 'autofill': False},
           'rent_10k_krw': {'value': 55, 'status': 'read', 'autofill': False}}      # 한 엔진만 읽은 항목은 채우지 않는다
    result = adapt_cards([], imf)
    assert result['extraction_status'] == 'EXTRACTED_NEEDS_REVIEW'
    assert list(result['fields']) == ['address_text']
    from backend.app.input_review import listing_draft
    draft = listing_draft({'id': 'x', 'result': result})
    assert draft['draft']['listing']['address_text'] == '서울 마포구 합정동 10-2' and draft['draft']['listing']['rent_10k_krw'] is None
    assert draft['draft']['confirmation']['user_confirmed'] is False
    assert 'rent_10k_krw' in draft['missing_or_unknown_fields']


def test_nothing_read_stays_no_listing_found():
    assert adapt_cards([], {'address_text': {'value': None, 'status': 'missing', 'autofill': False}})['extraction_status'] == 'NO_LISTING_FOUND'


def test_engine_image_fields_are_merged_by_agreement():
    from backend.app.local_ocr import merge_image_fields
    a = {'address_text': '서울 마포구 합정동 10-2', 'rent_10k_krw': 55.0}
    b = {'address_text': '서울 마포구 합정동 10-2', 'rent_10k_krw': 65.0}
    m = merge_image_fields({'easyocr': a, 'paddle': b})
    assert m['address_text']['autofill'] is True and m['rent_10k_krw']['status'] == 'conflict' and m['rent_10k_krw']['autofill'] is False
    assert merge_image_fields({'easyocr': a}) == {}                       # 엔진이 둘이 아니면 합의하지 않는다


def test_card_consensus_endpoint_accepts_missing_fields(tmp_path):
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
    from backend.app.config import Settings
    with TestClient(create_app(Settings(db_path=tmp_path / 'p.sqlite3', database_url='', clean_csv=tmp_path / 'none.csv'))) as c:
        c.headers['Authorization'] = 'Bearer ' + c.post('/sessions').json()['token']
        read = dict(contract_type='월세', deposit_10k_krw=1000, rent_10k_krw=55, area_m2=20.8, maintenance_10k_krw=None)
        r = c.post('/extraction/card-consensus', json={'engine_reads': {'a': [read], 'b': [read]}})
        assert r.status_code == 200, r.text
        assert r.json()['summary']['extracted'] == 1 and r.json()['cards'][0]['fields']['maintenance_10k_krw']['value'] is None
