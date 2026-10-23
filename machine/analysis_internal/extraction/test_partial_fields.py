# -*- coding: utf-8 -*-
"""부분 입력 시험(OCR 패키지 없이). 항목이 일부만 보여도 읽은 항목만 입력되고, 불일치·미표기 항목은 비워지는지 확인한다. 사용: python test_partial_fields.py"""
from consensus import consensus
from partial_fields import address_candidates, image_fields, merge_image_fields, partial_cards
from read_cards import KEY, cards_from_boxes
from test_read_cards import box


def main():
    bad = []
    # 1) 관리비 표기가 없거나 '없음'인 카드도 읽는다(예전 파서는 통째로 버림). 없음=0.0 은 명시된 경우만, 미표기는 None
    cards = partial_cards('월세 500/50\n원룸\n2층, 23.14m², 관리비 5만\n월세 300/40\n원룸\n3층, 19.8m²\n월세 200/30\n원룸\n4층, 20m², 관리비 없음\n')
    if cards != [('월세', 500.0, 50.0, 23.14, 5.0), ('월세', 300.0, 40.0, 19.8, None), ('월세', 200.0, 30.0, 20.0, 0.0)]:
        bad.append(('카드 부분 파싱', cards))
    # 2) 값이 비정상이면 그 항목만 비우고 카드는 유지(보정하지 않음), 머리줄이 비정상이면 카드를 읽지 않는다
    cards = partial_cards('월세 500/50 3층, 999m², 관리비 900만 월세 500/5000 2층, 20m², 관리비 5만')
    if cards != [('월세', 500.0, 50.0, None, None)]:
        bad.append(('비정상 범위', cards))
    # 3) 박스 → 카드: 관리비가 없는 카드가 살아난다(두 엔진이 같게 읽으면 그대로 합의)
    boxes = [box(15, 100, '월세 1000/52'), box(15, 160, '원룸'), box(15, 190, '3층, 27m²', 170)]
    one = cards_from_boxes(boxes, 400)
    if one != {('월세', 1000.0, 52.0, 27.0, None)}:
        bad.append(('박스 부분 읽기', one))
    res = consensus({'a': sorted(one), 'b': sorted(one)})
    if len(res) != 1 or res[0]['status'] != 'extracted' or res[0]['fields']['maintenance_10k_krw']['value'] is not None or res[0]['fields']['area_m2']['value'] != 27.0:
        bad.append(('관리비 없는 카드 합의', res))
    # 4) 같은 머리줄에서 한 항목만 엔진이 다르면: 일치한 항목은 채우고 다른 항목은 conflict 로 비운다
    A1 = ('월세', 1000.0, 52.0, 27.0, 9.0)
    A2 = ('월세', 1000.0, 52.0, 27.0, 5.0)
    res = consensus({'a': [A1], 'b': [A2]})
    if len(res) != 1 or res[0]['status'] != 'partial':
        bad.append(('부분 합의 상태', res))
    else:
        f = res[0]['fields']
        if f['area_m2'] != {'value': 27.0, 'status': 'agreed'} or f['maintenance_10k_krw'] != {'value': None, 'status': 'conflict'} or f['rent_10k_krw']['value'] != 52.0:
            bad.append(('부분 합의 항목', f))
    # 5) 한 엔진은 관리비를 못 읽고 다른 엔진만 읽은 경우: 한 엔진 값은 채우지 않는다(read)
    res = consensus({'a': [('월세', 1000.0, 52.0, 27.0, None)], 'b': [A1]})
    f = res[0]['fields'] if len(res) == 1 else {}
    if not f or f['maintenance_10k_krw'] != {'value': None, 'status': 'read'} or f['area_m2']['value'] != 27.0:
        bad.append(('단독 읽은 항목', res))
    # 6) 같은 머리줄 카드를 한 엔진이 여러 개 읽으면(서로 다른 카드일 수 있음) 항목을 섞지 않고 확인 필요
    B1 = ('월세', 1000.0, 52.0, 30.0, 9.0)
    res = consensus({'a': [A1, B1], 'b': [('월세', 1000.0, 52.0, 27.0, 5.0)]})
    if [c['status'] for c in res] != ['needs_review']:
        bad.append(('같은 머리줄 여러 카드', res))
    # 7) 기존 동작 유지: 머리줄이 서로 다르고 면적·관리비가 같으면 needs_review, 단독 읽기는 on_hold
    res = consensus({'a': [('월세', 1000.0, 40.0, 23.14, 8.0)], 'b': [('월세', 500.0, 40.0, 23.14, 8.0)]})
    if [c['status'] for c in res] != ['needs_review']:
        bad.append(('머리줄 불일치', res))
    # 8) 주소: 후보를 찾되 여러 개면 읽지 않고, 정규화한다
    t = '위치 서울특별시 관악구 봉천동 123-4 월세 1000/55'
    if address_candidates(t) != ['서울 관악구 봉천동 123-4']:
        bad.append(('주소 후보', address_candidates(t)))
    if 'address_text' in image_fields('서울 관악구 봉천동 12  서울 마포구 합정동 5'):
        bad.append(('주소가 여럿이면 읽지 않아야 함',))
    if address_candidates('월세 1000/55 3층 20m²'):
        bad.append(('주소가 없는데 후보가 생김', address_candidates('월세 1000/55 3층 20m²')))
    # 9) 이미지 단위: 라벨 기반으로 읽은 항목만 + 엔진 합의(agreed/read/conflict/missing)
    txt = '서울 관악구 봉천동 123-4  월세 1000/55  전용면적 23.14m²  관리비 5만원'
    f = image_fields(txt)
    if f != {'contract_type': '월세', 'deposit_10k_krw': 1000.0, 'rent_10k_krw': 55.0, 'area_m2': 23.14, 'maintenance_10k_krw': 5.0, 'address_text': '서울 관악구 봉천동 123-4'}:
        bad.append(('이미지 항목', f))
    m = merge_image_fields({'a': f, 'b': dict(f, area_m2=23.0, maintenance_10k_krw=None)})
    if m['address_text']['status'] != 'agreed' or m['area_m2']['status'] != 'conflict' or m['maintenance_10k_krw']['status'] != 'read' or m['address_text'].get('resolution') != 'candidate_needs_address_search':
        bad.append(('이미지 항목 합의', m))
    # 10) 주소만 있는 사진: 주소만 입력 후보, 나머지는 missing
    m = merge_image_fields({'a': image_fields('서울 마포구 합정동 10-2'), 'b': image_fields('서울 마포구 합정동 10-2')})
    if m['address_text']['value'] != '서울 마포구 합정동 10-2' or not m['address_text']['autofill'] or any(m[k]['status'] != 'missing' for k in ('deposit_10k_krw', 'rent_10k_krw', 'area_m2', 'maintenance_10k_krw')):
        bad.append(('주소만 있는 사진', m))
    # 11) 조각 경계: 잘린 카드 뒤에 다음 조각의 다른 카드 글('관리비 없음')이 붙어 항목이 섞이면 안 된다
    from partial_fields import TILE_MARK
    cards = partial_cards('월세 7000/50 3층, 20m²' + chr(10) + TILE_MARK + chr(10) + '관리비 없음' + chr(10) + '월세 200/30 2층, 19m², 관리비 5만')
    if cards != [('월세', 7000.0, 50.0, 20.0, None), ('월세', 200.0, 30.0, 19.0, 5.0)]:
        bad.append(('조각 경계 오염', cards))
    # 12) 월세 카드인데 월세 금액이 없는(금액 표기가 깨진) 머리줄은 읽지 않는다. 전세는 월세 금액이 없어도 된다
    cards = partial_cards('월세 3.000 2층, 20m², 관리비 5만 전세 15000 3층, 30m²')
    if cards != [('전세', 15000.0, None, 30.0, None)]:
        bad.append(('금액이 깨진 월세 머리줄', cards))
    print('실패 %d 건' % len(bad), *bad, sep='\n' if bad else ' ')
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
