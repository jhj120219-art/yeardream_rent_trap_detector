#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyze_listing 상태·라벨·경고 규칙 테스트 (실제 풀 + 통제된 가상 풀).
실행: python test_analyze.py  ->  output/test_analyze_results.csv
"""
import json
from pathlib import Path
import pandas as pd
import analyze as an
import compare_rent as cr

HERE = Path(__file__).parent
real = an.load_pool()


def synth(n=40, usage='아파트', gu='관악구', dong='봉천동', basement=False, base_rent=50, spread=2,
          dates='2026-09-01', area=59.9, dep=5000.0, arch=2005.0):
    rows = []
    for i in range(n):
        rows.append(dict(gu=gu, dong=dong, usage=usage, area=area, dep=dep, rent=base_rent + (i % (2 * spread + 1)) - spread,
                         arch=arch, basement=basement, is_new=True, date=pd.Timestamp(dates) + pd.Timedelta(days=i % 20),
                         dup_suspect=False))
    pool = cr.Pool(pd.DataFrame(rows))
    pool.dong_by_code = {'1162010100': '봉천동'}
    pool.dongs = {(gu, dong), ('관악구', '봉천동'), ('관악구', '신림동')}
    return pool


def P(**kw):
    d = dict(district_code='11620', dong='봉천동', building_type='APARTMENT', area_m2=59.9, area_basis='EXCLUSIVE',
             deposit_10k_krw=5000, rent_10k_krw=50, built_year=2005, floor=5, as_of='2026-10-01')
    d.update(kw)
    return d


results = []


def check(name, res, expect):
    ok = all((res.get(k) == v) if not callable(v) else v(res.get(k)) for k, v in expect.items())
    results.append({'테스트': name, '기대': str({k: (v if not callable(v) else '조건') for k, v in expect.items()}),
                    '실제': str({k: res.get(k) for k in expect}), '통과': 'PASS' if ok else 'FAIL'})
    return res


SP = synth()
# --- 입력/범위
check('지원하지 않는 자치구 -> OUT_OF_SCOPE', an.analyze_listing(P(district_code='11110'), real), {'status': 'OUT_OF_SCOPE'})
check('지원하지 않는 주택 유형 -> OUT_OF_SCOPE', an.analyze_listing(P(building_type='HOUSE_BOAT'), real), {'status': 'OUT_OF_SCOPE'})
check('동/법정동코드 없음 -> INPUT_REVIEW_REQUIRED', an.analyze_listing(P(dong=None), real), {'status': 'INPUT_REVIEW_REQUIRED'})
check('면적 3㎡ -> INPUT_REVIEW_REQUIRED', an.analyze_listing(P(area_m2=3), real), {'status': 'INPUT_REVIEW_REQUIRED'})
check('월세 0 -> INPUT_REVIEW_REQUIRED', an.analyze_listing(P(rent_10k_krw=0), real), {'status': 'INPUT_REVIEW_REQUIRED'})
check('법정동 코드가 다른 구 -> INPUT_REVIEW_REQUIRED', an.analyze_listing(P(dong=None, legal_dong_code='1144010100'), real),
      {'status': 'INPUT_REVIEW_REQUIRED'})
check('area_basis 값 오류 -> INPUT_REVIEW_REQUIRED', an.analyze_listing(P(area_basis='WRONG'), real), {'status': 'INPUT_REVIEW_REQUIRED'})
check('존재하지 않는 동 -> INPUT_REVIEW_REQUIRED', an.analyze_listing(P(dong='없는동'), real), {'status': 'INPUT_REVIEW_REQUIRED'})
# --- 라벨 (통제된 풀: 비교 40건, 월세 48~52, 신뢰도 높음)
r = check('아파트·전용면적·높음: 월세 80 -> COMPARED/UPPER_TAIL', an.analyze_listing(P(rent_10k_krw=80), SP),
          {'status': 'COMPARED', 'price_label': 'UPPER_TAIL', 'confidence_grade': 'HIGH', 'stage': 1})
check('월세 50 -> TYPICAL_RANGE', an.analyze_listing(P(rent_10k_krw=50), SP), {'status': 'COMPARED', 'price_label': 'TYPICAL_RANGE'})
check('월세 30 -> LOWER_RANGE', an.analyze_listing(P(rent_10k_krw=30), SP), {'status': 'COMPARED', 'price_label': 'LOWER_RANGE'})
check('월세 52 -> UPPER_RANGE 이하(UPPER_TAIL 아님)', an.analyze_listing(P(rent_10k_krw=52), SP),
      {'status': 'COMPARED', 'price_label': lambda v: v in ('UPPER_RANGE', 'TYPICAL_RANGE')})
# --- 면적 기준 / 층 / 단계 규칙
check('공급면적 입력 -> REFERENCE_ONLY + AREA_BASIS_MISMATCH', an.analyze_listing(P(area_basis='SUPPLY'), SP),
      {'status': 'REFERENCE_ONLY', 'price_label': 'UNRATED', 'warnings': lambda w: 'AREA_BASIS_MISMATCH' in w})
sp_mu = synth(usage='연립다세대')
check('연립다세대(면적 기준 확인됨·신뢰도 높음) -> COMPARED + 편차 경고', an.analyze_listing(P(building_type='MULTI_UNIT', rent_10k_krw=80), sp_mu),
      {'status': 'COMPARED', 'price_label': 'UPPER_TAIL',
       'warnings': lambda w: 'MULTI_UNIT_VARIANCE' in w and 'AREA_BASIS_UNVERIFIED' not in w})
sp_of = synth(usage='오피스텔', area=20.0)
check('오피스텔 전용면적 입력 -> COMPARED', an.analyze_listing(P(building_type='OFFICETEL', area_m2=20.0, rent_10k_krw=50), sp_of),
      {'status': 'COMPARED', 'price_label': 'TYPICAL_RANGE'})
check('면적 기준 UNKNOWN 이면 전용면적 가정 경고만(보류 아님)', an.analyze_listing(P(area_basis='UNKNOWN'), SP),
      {'status': 'COMPARED', 'warnings': lambda w: 'AREA_BASIS_ASSUMED_EXCLUSIVE' in w})
sp_dd = synth(usage='단독다가구')
sp_dd = synth(usage='단독다가구')
DD = dict(building_type='DETACHED_MULTI')
r_dd = check('단독다가구·지상층 확인·신뢰도 높음·월세 80 -> COMPARED/UPPER_RANGE(UPPER_TAIL 아님)', an.analyze_listing(P(**DD, floor=3, rent_10k_krw=80), sp_dd),
      {'status': 'COMPARED', 'price_label': 'UPPER_RANGE', 'confidence_grade': 'HIGH',
       'warnings': lambda w: all(x in w for x in ('FLOOR_UNCONFIRMED_COMPARABLES', 'DETACHED_STABILITY_RULE', 'AREA_BASIS_CONTRACT_AREA'))})
check('단독다가구 월세 54(Q75 위이지만 Q75×1.10 이하) -> TYPICAL_RANGE', an.analyze_listing(P(**DD, floor=3, rent_10k_krw=54), sp_dd),
      {'status': 'COMPARED', 'price_label': 'TYPICAL_RANGE'})
check('단독다가구 월세 500(극단값)도 UPPER_TAIL 금지', an.analyze_listing(P(**DD, floor=3, rent_10k_krw=500), sp_dd),
      {'price_label': 'UPPER_RANGE'})
check('단독다가구 월세 30 -> LOWER_RANGE', an.analyze_listing(P(**DD, floor=3, rent_10k_krw=30), sp_dd), {'price_label': 'LOWER_RANGE'})
check('단독다가구 floor_type=GROUND(광고 추출) -> COMPARED', an.analyze_listing(P(**DD, floor=0, floor_type='GROUND', floor_source='AD_EXTRACTED', rent_10k_krw=80), sp_dd),
      {'status': 'COMPARED', 'floor': lambda f: f['listing_floor_type'] == 'GROUND' and f['listing_floor_source'] == 'AD_EXTRACTED' and f['comparable_floor_known'] is False})
check('단독다가구 반지하(floor_type=BASEMENT) -> REFERENCE_ONLY + BASEMENT_LISTING', an.analyze_listing(P(**DD, floor=0, floor_type='BASEMENT', rent_10k_krw=80), sp_dd),
      {'status': 'REFERENCE_ONLY', 'price_label': 'UNRATED', 'warnings': lambda w: 'BASEMENT_LISTING' in w})
check('단독다가구 층 숫자 -1 -> REFERENCE_ONLY', an.analyze_listing(P(**DD, floor=-1, rent_10k_krw=80), sp_dd), {'status': 'REFERENCE_ONLY'})
sp_dd_mid = synth(usage='단독다가구', n=20, dates='2025-11-01')
check('단독다가구 신뢰도 보통 -> REFERENCE_ONLY(높음만 판정)', an.analyze_listing(P(**DD, floor=3, rent_10k_krw=80), sp_dd_mid),
      {'status': 'REFERENCE_ONLY', 'confidence_grade': 'MEDIUM', 'hold_reasons': lambda h: 'detached_requires_high_confidence' in h})
check('단독다가구 공급면적 입력 -> REFERENCE_ONLY', an.analyze_listing(P(**DD, floor=3, area_basis='SUPPLY', rent_10k_krw=80), sp_dd),
      {'status': 'REFERENCE_ONLY', 'warnings': lambda w: 'AREA_BASIS_MISMATCH' in w})
check('단독다가구 계약면적 입력(RENTAL_REPORTED) -> 경고 없이 COMPARED', an.analyze_listing(P(**DD, floor=3, area_basis='RENTAL_REPORTED', rent_10k_krw=80), sp_dd),
      {'status': 'COMPARED', 'warnings': lambda w: 'AREA_BASIS_CONTRACT_AREA' not in w and 'AREA_BASIS_MISMATCH' not in w})
check('floor_type 값 오류 -> INPUT_REVIEW_REQUIRED', an.analyze_listing(P(**DD, floor_type='ATTIC'), sp_dd), {'status': 'INPUT_REVIEW_REQUIRED'})
check('단독다가구 -> REFERENCE_ONLY + FLOOR_UNKNOWN', an.analyze_listing(P(building_type='DETACHED_MULTI', floor=0, rent_10k_krw=80), sp_dd),
      {'status': 'REFERENCE_ONLY', 'warnings': lambda w: 'FLOOR_UNKNOWN' in w,
       'hold_reasons': lambda h: 'floor_unknown' in h})
check('단독다가구도 가격 범위는 제공', an.analyze_listing(P(building_type='DETACHED_MULTI', floor=0), sp_dd),
      {'prices_10k_krw': lambda v: isinstance(v, dict) and v.get('median') is not None})
sp_b = synth(basement=True)
check('지하(floor=-1) -> 지하 거래끼리 비교 + 경고', an.analyze_listing(P(floor=-1), sp_b),
      {'status': 'COMPARED', 'warnings': lambda w: 'BASEMENT_COMPARED_SEPARATELY' in w})
check('지하 매물인데 지하 거래가 없는 풀 -> INSUFFICIENT_DATA', an.analyze_listing(P(floor=-1), SP), {'status': 'INSUFFICIENT_DATA'})
sp3 = cr.Pool(pd.concat([synth(n=3).__dict__.get('x', pd.DataFrame())] if False else [pd.DataFrame(
    [dict(gu='관악구', dong='봉천동', usage='아파트', area=59.9, dep=5000.0, rent=50 + (i % 3) - 1, arch=2005.0, basement=False,
          is_new=True, date=pd.Timestamp('2026-09-01') + pd.Timedelta(days=i), dup_suspect=False) for i in range(3)] +
    [dict(gu='관악구', dong='신림동', usage='아파트', area=64.0, dep=5000.0, rent=50 + (i % 3) - 1, arch=2005.0, basement=False,
          is_new=True, date=pd.Timestamp('2026-09-01') + pd.Timedelta(days=i), dup_suspect=False) for i in range(8)])]))
sp3.dong_by_code = {}; sp3.dongs = {('관악구', '봉천동'), ('관악구', '신림동')}
check('3차(같은 구 전체) 확대 -> REFERENCE_ONLY', an.analyze_listing(P(), sp3),
      {'status': 'REFERENCE_ONLY', 'stage': 3, 'warnings': lambda w: 'STAGE3_SAME_GU' in w and 'RELAXED_CONDITIONS' in w})
check('비교 사례 부족 -> INSUFFICIENT_DATA', an.analyze_listing(P(area_m2=190, deposit_10k_krw=90000), real), {'status': 'INSUFFICIENT_DATA'})
check('낮은 신뢰도 -> 판정 보류', an.analyze_listing(P(), sp3), {'price_label': 'UNRATED'})
# --- 데이터 최신성, 법정동 코드, 한글 용도명
check('기준일이 너무 멀면 DATA_STALE', an.analyze_listing(P(as_of='2027-03-01'), SP),
      {'warnings': lambda w: 'DATA_STALE' in w})
rc = an.analyze_listing(dict(district_code='11620', legal_dong_code='1162010100', building_type='아파트', area_m2=59.9,
                              area_basis='EXCLUSIVE', deposit_10k_krw=5000, rent_10k_krw=120, built_year=2005, floor=7), real)
check('실제 풀·법정동 코드·한글 용도명 -> COMPARED 또는 REFERENCE_ONLY', rc,
      {'status': lambda s: s in ('COMPARED', 'REFERENCE_ONLY'), 'comparison': lambda c: c and c['dong'] == '봉천동'})
# --- 일반 규칙
all_res = [an.analyze_listing(P(rent_10k_krw=x), SP) for x in (30, 50, 80)] + [rc]
ok_enum = all(r['status'] in an.ENUM_STATUS and r['price_label'] in an.ENUM_LABEL for r in all_res)
results.append({'테스트': 'status·price_label 이 정의된 값만 사용', '기대': 'enum 안', '실제': str(ok_enum), '통과': 'PASS' if ok_enum else 'FAIL'})
try:
    json.dumps(all_res, ensure_ascii=False); js = True
except Exception as e:
    js = False
results.append({'테스트': '결과가 JSON 직렬화 가능', '기대': 'True', '실제': str(js), '통과': 'PASS' if js else 'FAIL'})
texts = ' '.join(' '.join(r.get('messages', [])) + ' ' + ' '.join(r.get('warning_texts', {}).values()) for r in all_res + [
    an.analyze_listing(P(area_basis='SUPPLY'), SP), an.analyze_listing(P(building_type='DETACHED_MULTI', floor=0), sp_dd)])
bad = [w for w in ('함정', '사기', '불법', '바가지') if w in texts]
results.append({'테스트': '사용자 문구에 "함정/사기/불법/바가지" 표현 없음', '기대': '없음', '실제': str(bad), '통과': 'PASS' if not bad else 'FAIL'})
# 높음 등급이어도 REFERENCE_ONLY 에서는 UPPER_* 판정을 내지 않는지
rr = an.analyze_listing(P(area_basis='SUPPLY', rent_10k_krw=80), SP)
results.append({'테스트': '판정 보류 상태에서는 UPPER_*/LOWER_* 라벨 없음', '기대': 'UNRATED', '실제': rr['price_label'],
                '통과': 'PASS' if rr['price_label'] == 'UNRATED' else 'FAIL'})

df = pd.DataFrame(results)
df.to_csv(HERE / 'output' / 'test_analyze_results.csv', index=False, encoding='utf-8-sig')
print(df[['테스트', '통과']].to_string(index=False))
print(f"\n통과 {(df['통과'] == 'PASS').sum()} / {len(df)}")
for _, r in df[df['통과'] == 'FAIL'].iterrows():
    print('FAIL ->', r['테스트'], '| 기대', r['기대'], '| 실제', r['실제'])
