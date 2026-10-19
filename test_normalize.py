#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""normalize_listing / classify_floor_text / analyze_raw 테스트 (층 테스트 F01~F12 포함).
실행: python test_normalize.py -> output/test_normalize_results.csv
"""
from pathlib import Path
import pandas as pd
import analyze as an
import normalize_listing as nl
import compare_rent as cr

HERE = Path(__file__).parent
results = []


def check(name, cond, detail=''):
    results.append({'테스트': name, '통과': 'PASS' if cond else 'FAIL', '상세': str(detail)[:160]})


# ---------------- 층 문구 분류 (F01~F11)
def F(tid, text, ftype, floor='ANY', review=None):
    r = nl.classify_floor_text(text)
    ok = r['floor_type'] == ftype and (floor == 'ANY' or r['floor'] == floor) and (review is None or r['review_required'] == review)
    check(f'{tid} "{text}" -> {ftype}' + ('' if floor == 'ANY' else f', floor={floor}'), ok, r)


F('F01', '반지하 원룸', 'BASEMENT')
F('F02', '지층 1000/45', 'BASEMENT')
F('F03', 'B1 원룸', 'BASEMENT')
F('F04', '지하주차장 있음', 'UNKNOWN')
F('F05', '저층 원룸', 'UNKNOWN')
F('F06', '4층 건물', 'UNKNOWN', floor=None)
r = nl.classify_floor_text('4층 건물'); check('F06 총 층수만 추출(total_floors=4, floor=None)', r['total_floors'] == 4 and r['floor'] is None, r)
F('F07', '4층 중 3층', 'GROUND', floor=3, review=False)
r = nl.classify_floor_text('4층 중 3층'); check('F07 total_floors=4', r['total_floors'] == 4, r)
F('F08', '1층 매물', 'GROUND', floor=1)
F('F09', '1층인데 실제 반지하', 'BASEMENT', review=True)
F('F10', '층 정보 없음', 'UNKNOWN')
F('F11', '1층 매물, 3층 매물 동시 노출', 'UNKNOWN')
r = nl.classify_floor_text('1층 매물, 3층 매물 동시 노출'); check('F11 다중 매물 사유 표시', r['reason'] == 'MULTIPLE_LISTINGS', r)
F('F-extra1', '4층', 'UNKNOWN', floor=None, review=True)
F('F-extra2', '지하 1층 매물', 'BASEMENT', floor=-1)
F('F-extra3', '', 'UNKNOWN')

# ---------------- 변환
BASE = {'schema_version': '1.1',
        'listing': dict(district_code='11620', legal_dong_code='1162010200', building_type='SINGLE_MULTI_HOUSEHOLD', area_m2=25.0,
                        area_basis='CONTRACT', deposit_10k_krw=1000, rent_10k_krw=50, built_year=2015, floor=2,
                        floor_type='GROUND', floor_source='USER_CONFIRMED'),
        'options': {'maintenance_10k_krw': 7, 'internet_status': 'UNKNOWN'},
        'confirmation': {'user_confirmed': True, 'confirmed_fields': ['address', 'area_m2', 'floor_type']}}


def clone(**kw):
    import copy
    d = copy.deepcopy(BASE)
    for k, v in kw.items():
        if k in ('options', 'confirmation'):
            d[k].update(v)
        else:
            d['listing'][k] = v
    return d


n = nl.normalize_listing(BASE)
check('v1.1 입력 정상 변환', n['ok'] and n['payload']['building_type'] == 'DETACHED_MULTI' and n['payload']['area_basis'] == 'CONTRACT'
      and n['payload']['floor_type'] == 'GROUND' and n['payload']['legal_dong_code'] == '1162010200', n)
check('옵션은 시세 입력과 분리(options)', n['options'].get('maintenance_10k_krw') == 7 and 'maintenance_10k_krw' not in n['payload'], n['options'])
check('user_confirmed 없으면 USER_CONFIRMATION_REQUIRED', 'USER_CONFIRMATION_REQUIRED' in nl.normalize_listing(clone(confirmation={'user_confirmed': False}))['issues'])
check('floor=0 -> 미확인(None), 층 유형도 판정에 쓰지 않음(확인 목록에 floor_type 없음 + 출처 불명)',
      'floor' not in nl.normalize_listing(clone(floor=0, floor_type='GROUND', floor_source='IMAGE_EXTRACTED', confirmation={'confirmed_fields': ['address']}))['payload'])
n2 = nl.normalize_listing(clone(floor=3, floor_type='GROUND', floor_source='IMAGE_EXTRACTED', confirmation={'confirmed_fields': ['address']}))
check('AI 추출 GROUND 는 사용자 확인 전 판정 근거에서 제외', 'floor_type' not in n2['payload'] and n2['floor_final']['floor_trusted'] is False, n2)
n3 = nl.normalize_listing(clone(district_code=11620))
check('district_code 숫자 입력도 5자리 문자열로 변환', n3['payload']['district_code'] == '11620', n3['payload'])
check('district_code 4자리면 ADDRESS_REVIEW_REQUIRED', 'ADDRESS_REVIEW_REQUIRED' in nl.normalize_listing(clone(district_code='1162'))['issues'])
check('building_type "빌라"는 모호 -> 확인 필요', 'BUILDING_TYPE_REVIEW_REQUIRED' in nl.normalize_listing(clone(building_type='빌라'))['issues'])
check('금액 문자열 "1,000" 변환', nl.normalize_listing(clone(deposit_10k_krw='1,000'))['payload']['deposit_10k_krw'] == 1000.0)
check('월세 0 -> RENT_REVIEW_REQUIRED', 'RENT_REVIEW_REQUIRED' in nl.normalize_listing(clone(rent_10k_krw=0))['issues'])
check('legal_dong_name 만 있으면 dong 으로 변환', nl.normalize_listing(clone(legal_dong_code=None, legal_dong_name='신림동'))['payload'].get('dong') == '신림동')
flat = {'input_source': 'IMAGE_REVIEWED', 'user_confirmed': True, 'district_code': '11620', 'legal_dong_name': '신림동', 'building_type': 'MULTI_UNIT',
        'area_m2': 26.45, 'area_basis': 'EXCLUSIVE', 'deposit_10k_krw': 1000, 'rent_10k_krw': 50, 'maintenance_10k_krw': 7, 'floor': 3}
nf = nl.normalize_listing(flat)
check('준비팩 평면 형식도 변환', nf['ok'] and nf['options'].get('maintenance_10k_krw') == 7, nf)
check('requires_address_confirmation 이면 입력 확인 요구', 'ADDRESS_REVIEW_REQUIRED' in nl.normalize_listing(dict(flat, requires_address_confirmation=True))['issues'])

# ---------------- 분석까지 연결 (통제된 가상 풀)
def synth(usage, n=40, base_rent=50, area=25.0):
    rows = [dict(gu='관악구', dong='신림동', usage=usage, area=area, dep=1000.0, rent=base_rent + (i % 5) - 2, arch=2015.0, basement=False,
                 is_new=True, date=pd.Timestamp('2026-09-01') + pd.Timedelta(days=i % 20), dup_suspect=False) for i in range(n)]
    p = cr.Pool(pd.DataFrame(rows)); p.dong_by_code = {'1162010200': '신림동'}; p.dongs = {('관악구', '신림동')}
    return p


pool_dd = synth('단독다가구')
r = nl.analyze_raw(clone(rent_10k_krw=80, as_of='2026-10-01'), pool_dd)
check('단독다가구 + 사용자 확인 지상층 + 높음 -> COMPARED/UPPER_RANGE', r['status'] == 'COMPARED' and r['price_label'] == 'UPPER_RANGE', (r['status'], r['price_label']))
check('결과에 reference/confidence_details/reason_codes 포함', all(k in r for k in ('reference', 'confidence_details', 'reason_codes')) and r['reference']['contract_type'] == 'NEW', list(r)[:20])
check('reference 에 renewals_excluded=True, months_used, search_stage, sample_count', r['reference']['renewals_excluded'] is True and r['reference']['months_used'] == 12
      and r['reference']['search_stage'] == 1 and r['reference']['sample_count'] >= 10, r['reference'])
# F12: AI 추출은 GROUND, 사용자 수정은 BASEMENT -> 사용자 수정 반영, 판정 보류
f12 = clone(rent_10k_krw=80, as_of='2026-10-01', floor=0, floor_type='BASEMENT', floor_source='USER_CONFIRMED')
r12 = nl.analyze_raw(f12, pool_dd)
check('F12 AI GROUND -> 사용자 BASEMENT 수정 시 REFERENCE_ONLY', r12['status'] == 'REFERENCE_ONLY' and 'BASEMENT_LISTING' in r12['warnings'], (r12['status'], r12['warnings']))
r_unc = nl.analyze_raw(clone(rent_10k_krw=80, as_of='2026-10-01', floor=3, floor_type='GROUND', floor_source='IMAGE_EXTRACTED',
                              confirmation={'confirmed_fields': ['address']}), pool_dd)
check('AI 추출 지상층(사용자 미확인)이면 단독다가구 판정 실행 안 됨', r_unc['status'] == 'REFERENCE_ONLY' and r_unc['price_label'] == 'UNRATED', (r_unc['status'], r_unc['hold_reasons']))
r_in = nl.analyze_raw(clone(confirmation={'user_confirmed': False}), pool_dd)
check('미확인 입력은 분석하지 않고 INPUT_REVIEW_REQUIRED', r_in['status'] == 'INPUT_REVIEW_REQUIRED' and 'USER_CONFIRMATION_REQUIRED' in r_in['input_issues'])
check('SINGLE_MULTI_HOUSEHOLD 별칭이 analyze_listing 에서도 허용',
      an.analyze_listing(dict(district_code='11620', dong='신림동', building_type='SINGLE_MULTI_HOUSEHOLD', area_m2=25, area_basis='CONTRACT',
                              deposit_10k_krw=1000, rent_10k_krw=50, floor=2, as_of='2026-10-01'), pool_dd)['status'] in ('COMPARED', 'REFERENCE_ONLY'))
check('CONTRACT 면적 기준은 단독다가구 AREA_BASIS_CONTRACT_AREA 경고 없음', 'AREA_BASIS_CONTRACT_AREA' not in r['warnings'] and 'AREA_BASIS_MISMATCH' not in r['warnings'], r['warnings'])

df = pd.DataFrame(results)
df.to_csv(HERE / 'output' / 'test_normalize_results.csv', index=False, encoding='utf-8-sig')
print(df[['테스트', '통과']].to_string(index=False))
print(f"\n통과 {(df['통과'] == 'PASS').sum()} / {len(df)}")
for _, x in df[df['통과'] == 'FAIL'].iterrows():
    print('FAIL ->', x['테스트'], '|', x['상세'])
