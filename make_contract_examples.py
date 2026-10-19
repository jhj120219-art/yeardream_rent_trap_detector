#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계약 v1.1 상태별 예시 JSON 생성(실제 비교 풀로 계산한 값, 매물은 가상). 실행: python make_contract_examples.py"""
import copy, json
from pathlib import Path
import analyze as an
import normalize_listing as nl

HERE = Path(__file__).parent
OUT = HERE / 'contract' / 'examples'
pool = an.load_pool()


def listing(**kw):
    d = dict(district_code='11620', legal_dong_code='1162010100', building_type='APARTMENT', area_m2=59.9, area_basis='EXCLUSIVE',
             deposit_10k_krw=5000, rent_10k_krw=150, built_year=2005, floor=7, floor_type='GROUND', floor_source='USER_CONFIRMED')
    d.update(kw)
    return d


def wrap(l, confirmed=True, options=None):
    return {'schema_version': '1.1', 'listing': l, 'options': options or {'maintenance_10k_krw': 7, 'internet_status': 'UNKNOWN',
            'elevator_status': 'UNKNOWN', 'parking_status': 'UNKNOWN'},
            'confirmation': {'user_confirmed': confirmed, 'input_source': 'IMAGE_REVIEWED',
                             'confirmed_fields': ['address', 'building_type', 'area_m2', 'area_basis', 'deposit_10k_krw', 'rent_10k_krw', 'floor_type']}}


def save(name, inp, note):
    res = nl.analyze_raw(inp, pool)
    (OUT / f'{name}.json').write_text(json.dumps({'_note': note, 'input': inp, 'output': res}, ensure_ascii=False, indent=2), encoding='utf-8')
    return res


# 1) 정상 비교: 아파트 (월세를 실제 중앙값 근처로)
r0 = nl.analyze_raw(wrap(listing()), pool)
med = r0['prices_10k_krw']['median'] if r0.get('prices_10k_krw') else 150
r = save('01_COMPARED_apartment_typical', wrap(listing(rent_10k_krw=round(med))), '아파트·전용면적·시세 범위 안(가상 매물, 실제 풀 기준 계산)')
q = r0['prices_10k_krw']
r = save('02_COMPARED_apartment_upper', wrap(listing(rent_10k_krw=round(q['q90'] * 1.15))), '비교 분포 상위 10%를 넘는 가격대(가상 매물)')
# 3) 단독다가구: 지상층 확인 + 높음 + Q75×1.1 초과 -> UPPER_RANGE (실제 풀에서 후보 탐색)
found = None
for gu_code, dong_code in (('11620', '1162010200'), ('11620', '1162010100'), ('11590', None)):
    for area in (16.5, 18.0, 20.0, 23.0):
        l = listing(district_code=gu_code, legal_dong_code=dong_code, building_type='DETACHED_MULTI', area_m2=area, area_basis='CONTRACT',
                    deposit_10k_krw=1000, built_year=None, floor=3, rent_10k_krw=50)
        if dong_code is None:
            l.pop('legal_dong_code'); l['dong'] = '상도동'
        base = nl.analyze_raw(wrap(l), pool)
        if base.get('prices_10k_krw') and base['confidence_grade'] == 'HIGH':
            found = (l, base); break
    if found: break
if found:
    l, base = found
    l = dict(l, rent_10k_krw=round(base['prices_10k_krw']['q75'] * 1.25))
    save('03_COMPARED_detached_ground_confirmed_upper_range', wrap(l), '단독다가구: 지상층을 사용자가 확인 + 신뢰도 높음 + Q75×1.10 초과일 때만 "높은 편"(UPPER_RANGE)')
    save('04_REFERENCE_ONLY_detached_floor_unknown', wrap(dict(l, floor=None, floor_type='UNKNOWN', floor_source='UNKNOWN')),
         '단독다가구인데 층 미확인 -> 가격 범위만 제공(판정 없음)')
    save('05_REFERENCE_ONLY_detached_basement', wrap(dict(l, floor=-1, floor_type='BASEMENT')), '단독다가구 반지하/지하 -> 가격 범위만 제공')
# 6) 입력 확인 필요
save('06_INPUT_REVIEW_REQUIRED_not_confirmed', wrap(listing(), confirmed=False), '사용자가 확인하지 않은 입력(AI 추출 직후)')
save('07_INPUT_REVIEW_REQUIRED_bad_rent', wrap(listing(rent_10k_krw=0)), '월세 값이 올바르지 않음')
# 8) 지원 범위 밖
save('08_OUT_OF_SCOPE_district', wrap(listing(district_code='11110', legal_dong_code='1111010100')), '현재 지원하지 않는 자치구(종로구)')
# 9) 비교 사례 부족
save('09_INSUFFICIENT_DATA', wrap(listing(area_m2=190, deposit_10k_krw=90000, rent_10k_krw=400)), '비교 가능한 실거래가 10건 미만')
# 10) 면적 기준 불일치(공급면적 입력)
save('10_REFERENCE_ONLY_supply_area', wrap(listing(area_basis='SUPPLY')), '공급면적을 입력한 경우: 가격 판정 보류')
print('saved', len(list(OUT.glob('*.json'))), 'examples')
for f in sorted(OUT.glob('*.json')):
    d = json.loads(f.read_text(encoding='utf-8'))['output']
    print(f.name, '->', d['status'], d['price_label'], d['confidence_grade'], d.get('reason_codes'))
