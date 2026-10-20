#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""팀 연동용 진입점: analyze_listing(payload, pool) -> dict(JSON 직렬화 가능)

입력(payload)
  district_code  '11620'  (또는 gu_name '관악구')
  legal_dong_code '1162010100'(10자리, 선택) 또는 dong '신림동'
  building_type  APARTMENT | MULTI_UNIT(연립다세대) | DETACHED_MULTI(단독·다가구) | OFFICETEL  (한글 용도명도 허용)
  area_m2, area_basis(EXCLUSIVE|SUPPLY|RENTAL_REPORTED|UNKNOWN), deposit_10k_krw, rent_10k_krw
  built_year(선택), floor(선택; ≥1 지상, <0 지하, 0/None 은 '층 미확인'),
  floor_type(선택; GROUND|BASEMENT|UNKNOWN — 사용자·광고에서 확인한 층 유형), floor_source(선택; USER_CONFIRMED|AD_EXTRACTED),
  as_of(선택, 기본: 데이터 최신일+1)

출력 status: COMPARED | REFERENCE_ONLY | INSUFFICIENT_DATA | INPUT_REVIEW_REQUIRED | OUT_OF_SCOPE
출력 price_label: UPPER_TAIL | UPPER_RANGE | TYPICAL_RANGE | LOWER_RANGE | UNRATED
단독다가구: 실거래에 층이 없어 지하·지상이 섞인 비교군 -> 지상층 확인 + 신뢰도 높음 + 1·2차일 때만, 월세 > Q75×1.10 이면 UPPER_RANGE(최상위 라벨 금지).
최종 status/price_label 은 이 코드가 결정한다(프론트는 그대로 표시). '함정/사기'라는 표현은 사용자 문구에 쓰지 않는다.
"""
from __future__ import annotations
import datetime as _dt
from pathlib import Path
import numpy as np
import pandas as pd
import compare_rent as cr

DATA_SOURCE = '서울 열린데이터광장 부동산 전월세가 정보(tbLnOpendataRentV)'
SUPPORTED_GU = {'11620': '관악구', '11215': '광진구', '11440': '마포구', '11590': '동작구', '11500': '강서구', '11350': '노원구'}
GU_BY_NAME = {v: k for k, v in SUPPORTED_GU.items()}
BUILDING_TYPES = {
    'APARTMENT': '아파트', 'MULTI_UNIT': '연립다세대', 'DETACHED_MULTI': '단독다가구', 'SINGLE_MULTI_HOUSEHOLD': '단독다가구', 'OFFICETEL': '오피스텔',
    '아파트': '아파트', '연립다세대': '연립다세대', '단독다가구': '단독다가구', '오피스텔': '오피스텔',
}
# 서울시 RENT_AREA 는 국토부 실거래가 공개시스템 CSV의 면적 컬럼과 건별 대조에서 100% 일치(check_area_basis.py).
#  - 아파트·연립다세대·오피스텔: 국토부 컬럼명이 '전용면적(㎡)' -> 광고의 전용면적과 같은 기준.
#  - 단독다가구: 국토부 컬럼명이 '계약면적(㎡)'(임대차 계약서상 면적) -> 광고의 전용면적과 같다고 보증할 수 없음.
AREA_BASIS_VERIFIED = {'아파트': True, '연립다세대': True, '오피스텔': True, '단독다가구': False}
POLICY = {
    'hold_verdict_if_area_basis_unverified': True,    # 면적 기준 미확인 용도는 가격 판정 보류(REFERENCE_ONLY)
    'detached_conditional': True,                     # 단독다가구: 지상층 확인 시 조건부 판정 허용(False 면 항상 범위만)
    'detached_requires_grade': 'HIGH',                # 조건부 판정은 신뢰도 높음일 때만
    'detached_shift': 0.10,                           # 월세 > Q75×(1+0.10)일 때만 "높은 편"(가짜 결측 실험으로 정함)
    'hold_verdict_if_stage3': True,                   # 3차(같은 구 전체) 확대는 항상 참고용
}
STALE_DAYS = 45

ENUM_STATUS = ('COMPARED', 'REFERENCE_ONLY', 'INSUFFICIENT_DATA', 'INPUT_REVIEW_REQUIRED', 'OUT_OF_SCOPE')
ENUM_LABEL = ('UPPER_TAIL', 'UPPER_RANGE', 'TYPICAL_RANGE', 'LOWER_RANGE', 'UNRATED')
GRADE_EN = {'높음': 'HIGH', '보통': 'MEDIUM', '낮음': 'LOW', '보류': 'NONE'}

MESSAGES = {
    'UPPER_TAIL': '비슷한 조건의 실제 계약 중 상위 10%에 해당하는 높은 가격대입니다. 옵션·관리비·내부 상태 등 실거래 데이터에 없는 차이일 수 있으니 포함 항목과 추가 비용을 확인해 보세요.',
    'UPPER_RANGE': '비슷한 조건의 실제 계약보다 높은 편(상위 25% 이내)입니다. 포함 항목과 추가 비용을 확인해 보세요.',
    'TYPICAL_RANGE': '비슷한 조건의 실제 계약 가격대(중간 50%) 안에 있습니다.',
    'LOWER_RANGE': '비슷한 조건의 실제 계약보다 낮은 편(하위 25%)입니다. 낮은 이유(층·옵션·상태)를 확인해 보세요.',
    'UNRATED': '이 조건에서는 가격이 높은지 낮은지 판정하지 않고, 참고용 가격 범위만 보여드립니다.',
}
WARNING_TEXT = {
    'AREA_BASIS_UNVERIFIED': '단독·다가구의 실거래 면적은 계약서상 계약면적이라 광고의 전용면적과 같다고 보증할 수 없어 가격 판정을 하지 않습니다.',
    'AREA_BASIS_ASSUMED_EXCLUSIVE': '입력한 면적을 전용면적으로 가정해 비교했습니다. 광고의 면적이 전용면적인지 확인해 주세요.',
    'AREA_BASIS_MISMATCH': '입력한 면적이 전용면적이 아니어서(공급·계약면적 등) 실거래 비교에 그대로 쓸 수 없습니다.',
    'FLOOR_UNKNOWN': '매물이 지상층인지 확인되지 않았습니다. 단독·다가구는 층이 확인된 지상층 매물만 가격 판정을 합니다. 층(지상/반지하)을 알려 주세요.',
    'FLOOR_UNCONFIRMED_COMPARABLES': '단독·다가구 실거래에는 층 정보가 없어 지하·반지하 계약이 섞인 비교군입니다. 그 때문에 시세가 낮게 추정될 수 있어, 평소보다 더 높을 때만 "높은 편"으로 표시합니다.',
    'BASEMENT_LISTING': '지하·반지하 매물은 단독·다가구 비교군에서 층을 분리할 수 없어 가격 판정을 하지 않습니다.',
    'AREA_BASIS_CONTRACT_AREA': '단독·다가구 실거래의 면적은 계약서상 계약면적입니다. 광고에 적힌 면적과 기준이 다를 수 있습니다.',
    'DETACHED_STABILITY_RULE': '층 정보가 없는 비교군의 오차를 감안해 더 엄격한 기준(비교 상위 25% 구간의 1.1배 초과)을 적용했습니다.',
    'BASEMENT_COMPARED_SEPARATELY': '지하·반지하는 지상층과 분리해서 비교했습니다.',
    'STAGE3_SAME_GU': '같은 자치구 전체로 범위를 넓혀 비교했습니다. 생활권이 다른 지역의 거래가 포함될 수 있어 참고용입니다.',
    'RELAXED_CONDITIONS': '비교 조건(면적·건축연도·보증금·기간·지역)을 일부 넓혀서 찾은 결과입니다.',
    'LOW_CONFIDENCE': '비교 사례의 유사도나 충분도가 낮아 가격 판정을 하지 않습니다.',
    'MEDIUM_CONFIDENCE_CONFIRM': '신뢰도가 보통이어서 추가 확인이 필요합니다.',
    'MULTI_UNIT_VARIANCE': '연립다세대는 건물·호실 편차가 커서 실제 월세 오차가 큰 편입니다(검증 결과 중앙 오차 약 25%).',
    'BUILT_YEAR_MISSING': '건축연도를 입력하지 않아 건축연도 조건 없이 비교했습니다.',
    'DATA_STALE': '비교 데이터가 최신이 아닐 수 있습니다(최근 신고분 미반영).',
    'DONG_ASSUMED_FROM_CODE': '법정동 코드로 동을 확인했습니다.',
}


# ------------------------------------------------------------------ 풀 로딩
def load_pool(clean_csv: str | Path | None = None):
    """output/clean_rent_data.csv(run_validation.py 산출물)에서 비교 풀과 동 코드 사전을 만든다."""
    path = Path(clean_csv or Path(__file__).parent / 'output' / 'clean_rent_data.csv')
    rent = pd.read_csv(path, parse_dates=['date'], low_memory=False,
                       dtype={'CGG_CD': str, 'STDG_CD': str})
    for c in ('is_new', 'basement', 'dup_suspect'):
        rent[c] = rent[c].astype(bool)
    pool = cr.Pool(rent)
    pool.renewals_excluded_by_gu = {g: int((rent['gu'] == g).sum() - rent[(rent['gu'] == g) & rent['is_new']].shape[0])
                                    for g in rent['gu'].unique()}
    codes = (rent.assign(code=rent['CGG_CD'].str.zfill(5) + rent['STDG_CD'].str.zfill(5))
             .drop_duplicates('code').set_index('code')['dong'].to_dict())
    pool.dong_by_code = codes
    pool.dongs = {(g, d) for g, d in zip(rent['gu'], rent['dong'])}
    return pool


# ------------------------------------------------------------------ 검증
def _num(x):
    try:
        v = float(x)
        return None if np.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _base_result(status, **kw):
    out = dict(status=status, stage=None, sample_count=0, confidence_grade='NONE', price_label='UNRATED',
               prices_10k_krw=None, rent_difference_10k_krw=None, rent_difference_pct=None, percentile=None,
               warnings=[], messages=[], errors=[], relaxed=[], trust=None, data_source=DATA_SOURCE, data_as_of=None,
               reason_codes=[], hold_reasons=[], reference=None, confidence_details=None, floor=None)
    out.update(kw)
    return out


HOLD_TO_REASON = {'area_unverified': 'AREA_BASIS_UNVERIFIED', 'area_mismatch': 'AREA_BASIS_MISMATCH', 'floor_unknown': 'FLOOR_UNKNOWN',
                  'basement_listing': 'BASEMENT_LISTING', 'detached_requires_high_confidence': 'PRICE_LABEL_NOT_APPROVED',
                  'stage3': 'SEARCH_SCOPE_EXPANDED', 'low_confidence': 'LOW_CONFIDENCE'}
RELAX_CODES = {'area': 'AREA_RANGE_EXPANDED', 'arch': 'BUILT_YEAR_RANGE_EXPANDED', 'dep': 'DEPOSIT_RANGE_EXPANDED',
               'months': 'PERIOD_EXPANDED', 'scope': 'SEARCH_SCOPE_EXPANDED'}


def _reference(res, stage_name, pool, gu, q):
    """결과 설명 필드: 어떤 거래를 어떤 조건으로 비교했는지."""
    st = {s['name']: s for s in cr.STAGES}
    cur, first = st[stage_name], cr.STAGES[0]
    relaxed = [RELAX_CODES[k] for k in ('area', 'arch', 'dep', 'months', 'scope') if cur[k] != first[k]]
    renew = getattr(pool, 'renewals_excluded_by_gu', {}) or {}
    return {'source': DATA_SOURCE, 'contract_type': 'NEW', 'renewals_excluded': True,
            'renewals_excluded_in_data_for_gu': renew.get(gu),            # 해당 구 전체 데이터에서 제외한 갱신 계약 수(이 매물 검색 범위 안의 제외 건수가 아님)
            'months_used': cur['months'], 'search_stage': int(stage_name[0]), 'sample_count': int(res['n']),
            'conditions': {'area_tolerance': cur['area'], 'built_year_tolerance': cur['arch'], 'deposit_tolerance': cur['dep'],
                           'scope': '같은 법정동' if cur['scope'] == 'dong' else '같은 자치구 전체'},
            'relaxed_conditions': relaxed,
            'prices_10k_krw': {k: round(float(v), 1) for k, v in q.items()}}


def _reason_codes(hold, warns, stage_name, status):
    codes = [HOLD_TO_REASON[h] for h in hold if h in HOLD_TO_REASON]
    if stage_name == '3차' and 'SEARCH_SCOPE_EXPANDED' not in codes:
        codes.append('SEARCH_SCOPE_EXPANDED')
    if status == 'REFERENCE_ONLY' and not codes:
        codes.append('PRICE_LABEL_NOT_APPROVED')
    return list(dict.fromkeys(codes))


def analyze_listing(payload: dict, pool) -> dict:
    p = dict(payload or {})
    errors, warns = [], []
    # --- 지역
    gu_code = str(p.get('district_code') or '').strip()
    gu = SUPPORTED_GU.get(gu_code) or p.get('gu_name')
    if not gu_code and p.get('gu_name') in GU_BY_NAME:
        gu_code = GU_BY_NAME[p['gu_name']]
    data_as_of = str(pd.Timestamp(pool.max_date).date())
    if not gu_code and not p.get('gu_name'):
        return _base_result('INPUT_REVIEW_REQUIRED', errors=['district_code(또는 gu_name)가 필요합니다.'], data_as_of=data_as_of)
    if gu_code not in SUPPORTED_GU:
        return _base_result('OUT_OF_SCOPE', messages=['현재 시세 분석을 지원하는 지역은 %s입니다.' % ', '.join(SUPPORTED_GU.values())],
                            warnings=['UNSUPPORTED_DISTRICT'], data_as_of=data_as_of)
    gu = SUPPORTED_GU[gu_code]
    # --- 주택 유형
    usage = BUILDING_TYPES.get(str(p.get('building_type') or '').strip())
    if usage is None:
        return _base_result('OUT_OF_SCOPE', messages=['지원하는 주택 유형은 아파트·연립다세대·단독다가구·오피스텔입니다.'],
                            warnings=['UNSUPPORTED_BUILDING_TYPE'], data_as_of=data_as_of)
    # --- 동
    dong = p.get('dong')
    code = str(p.get('legal_dong_code') or '').strip()
    if code:
        if not code.startswith(gu_code):
            errors.append('법정동 코드가 선택한 자치구와 맞지 않습니다.')
        dong_c = getattr(pool, 'dong_by_code', {}).get(code)
        if dong_c is None:
            errors.append('법정동 코드를 데이터에서 찾을 수 없습니다.')
        else:
            if dong and dong != dong_c:
                errors.append('법정동 코드와 동 이름이 서로 다릅니다.')
            dong = dong_c
    if not dong:
        errors.append('dong 또는 legal_dong_code 가 필요합니다.')
    elif (gu, dong) not in getattr(pool, 'dongs', {(gu, dong)}):
        errors.append('해당 자치구에서 동 이름을 찾을 수 없습니다.')
    # --- 숫자 입력
    area, dep, rent = _num(p.get('area_m2')), _num(p.get('deposit_10k_krw')), _num(p.get('rent_10k_krw'))
    if area is None or not (5 <= area <= 200):
        errors.append('면적(㎡)은 5~200 사이여야 합니다.')
    if dep is None or dep < 0:
        errors.append('보증금(만원)은 0 이상이어야 합니다.')
    if rent is None or not (1 <= rent <= 500):
        errors.append('월세(만원)는 1~500 사이여야 합니다.')
    built = _num(p.get('built_year'))
    if built is not None and not (1950 <= built <= _dt.date.today().year + 1):
        errors.append('건축연도 값이 올바르지 않습니다.')
    floor = _num(p.get('floor'))
    basis = str(p.get('area_basis') or 'UNKNOWN').upper()
    if basis == 'CONTRACT':                       # 계약 v1.1 의 '계약면적' = 서울시 RENT_AREA 의 단독다가구 면적 기준(RENTAL_REPORTED 와 동일하게 취급)
        basis = 'RENTAL_REPORTED'
    if basis not in ('EXCLUSIVE', 'SUPPLY', 'RENTAL_REPORTED', 'UNKNOWN'):
        errors.append('area_basis 는 EXCLUSIVE|SUPPLY|CONTRACT|RENTAL_REPORTED|UNKNOWN 중 하나여야 합니다.')
    ftype = str(p.get('floor_type') or '').upper()
    if ftype and ftype not in ('GROUND', 'BASEMENT', 'UNKNOWN'):
        errors.append('floor_type 은 GROUND|BASEMENT|UNKNOWN 중 하나여야 합니다.')
    if errors:
        return _base_result('INPUT_REVIEW_REQUIRED', errors=errors, data_as_of=data_as_of)
    # --- 매물의 층 유형: floor 숫자(≥1 지상, <0 지하) 또는 사용자·광고에서 확인한 floor_type. 0/없음은 층 미확인.
    if floor is not None and floor >= 1:
        floor_type, floor_source = 'GROUND', 'USER_INPUT'
    elif floor is not None and floor < 0:
        floor_type, floor_source = 'BASEMENT', 'USER_INPUT'
    elif ftype in ('GROUND', 'BASEMENT'):
        floor_type, floor_source = ftype, str(p.get('floor_source') or 'USER_CONFIRMED').upper()
    else:
        floor_type, floor_source = 'UNKNOWN', 'NONE'
    # --- 비교 실행
    # 단독다가구 실거래에는 층이 없어 지하·지상이 섞인 한 풀로만 비교한다(지하 여부로 풀을 나누지 않음).
    basement = bool(floor_type == 'BASEMENT') and usage != '단독다가구'
    as_of = p.get('as_of')
    L = dict(gu=gu, dong=dong, usage=usage, area=area, deposit=dep, rent=rent, arch_year=built, basement=basement)
    res = cr.compare(L, pool, as_of=as_of)
    asof_ts = pd.Timestamp(as_of) if as_of else pd.Timestamp(pool.max_date) + pd.Timedelta(days=1)
    if (asof_ts - pd.Timestamp(pool.max_date)).days > STALE_DAYS:
        warns.append('DATA_STALE')
    if res['status'] != 'ok':
        out = _base_result('INSUFFICIENT_DATA', sample_count=res['n'] or 0, warnings=warns,
                           messages=['비슷한 조건의 실제 계약이 부족해 시세 판단을 보류합니다.'], data_as_of=data_as_of)
        out['trace'] = res['trace']
        return out
    grade_kr = res['trust']['grade']
    grade = GRADE_EN[grade_kr]
    stage = res['stage']
    if stage != '1차':
        warns.append('RELAXED_CONDITIONS')
    if stage == '3차':
        warns.append('STAGE3_SAME_GU')
    if basement:
        warns.append('BASEMENT_COMPARED_SEPARATELY')
    if usage == '연립다세대':
        warns.append('MULTI_UNIT_VARIANCE')
    if built is None:
        warns.append('BUILT_YEAR_MISSING')
    # --- 면적 기준
    hold = []
    if usage == '단독다가구':
        # 데이터의 면적은 계약서상 '계약면적'. 공급면적 입력만 보류하고, 전용/불명은 경고, 계약면적 입력은 기준 일치.
        if basis == 'SUPPLY':
            warns.append('AREA_BASIS_MISMATCH'); hold.append('area_mismatch')
        elif basis != 'RENTAL_REPORTED':
            warns.append('AREA_BASIS_CONTRACT_AREA')
    elif basis in ('SUPPLY', 'RENTAL_REPORTED'):
        warns.append('AREA_BASIS_MISMATCH'); hold.append('area_mismatch')
    elif POLICY['hold_verdict_if_area_basis_unverified'] and not AREA_BASIS_VERIFIED.get(usage, False):
        warns.append('AREA_BASIS_UNVERIFIED'); hold.append('area_unverified')
    elif basis == 'UNKNOWN':
        warns.append('AREA_BASIS_ASSUMED_EXCLUSIVE')       # 데이터 쪽 기준은 확인됨 -> 사용자가 입력한 면적을 전용면적으로 가정
    if usage == '단독다가구':
        warns.append('FLOOR_UNCONFIRMED_COMPARABLES')
        if floor_type == 'BASEMENT':
            warns.append('BASEMENT_LISTING'); hold.append('basement_listing')
        elif floor_type != 'GROUND' or not POLICY['detached_conditional']:
            warns.append('FLOOR_UNKNOWN'); hold.append('floor_unknown')
        if grade != POLICY['detached_requires_grade']:
            hold.append('detached_requires_high_confidence')
    if stage == '3차' and POLICY['hold_verdict_if_stage3']:
        hold.append('stage3')
    if grade == 'LOW':
        warns.append('LOW_CONFIDENCE'); hold.append('low_confidence')
    # --- 판정 라벨
    r = float(rent)
    q = {k: res[k] for k in ('q10', 'q25', 'median', 'q75', 'q90')}
    if hold:
        label = 'UNRATED'
    elif usage == '단독다가구':
        # 층을 확인한 지상층 매물만, 비교군에 지하 계약이 섞여 낮게 추정될 수 있어 Q75×(1+s) 초과일 때만 "높은 편". 최상위 라벨 금지.
        if r > q['q75'] * (1 + POLICY['detached_shift']):
            label = 'UPPER_RANGE'
            warns.append('DETACHED_STABILITY_RULE')
        elif r < q['q25']:
            label = 'LOWER_RANGE'
        else:
            label = 'TYPICAL_RANGE'
    elif r > q['q90'] and grade == 'HIGH':
        label = 'UPPER_TAIL'
    elif r > q['q75']:
        label = 'UPPER_RANGE'
        if grade == 'MEDIUM':
            warns.append('MEDIUM_CONFIDENCE_CONFIRM')
    elif r < q['q25']:
        label = 'LOWER_RANGE'
    else:
        label = 'TYPICAL_RANGE'
    if grade == 'MEDIUM' and label == 'UPPER_TAIL':       # 보통 등급은 최상위 단계 표시 금지
        label = 'UPPER_RANGE'
    # --- 상태
    status = 'REFERENCE_ONLY' if hold else 'COMPARED'
    msgs = [MESSAGES[label]] if status == 'COMPARED' else [MESSAGES['UNRATED']]
    msgs.append(res['message'])
    warns = list(dict.fromkeys(warns))
    out = _base_result(status, stage=int(stage[0]), sample_count=int(res['n']), confidence_grade=grade, price_label=label,
                       prices_10k_krw={k: round(float(v), 1) for k, v in q.items()},
                       rent_difference_10k_krw=round(r - res['median'], 1), rent_difference_pct=res['diff_pct'],
                       percentile=res['percentile'], warnings=warns, messages=msgs,
                       relaxed=[c for c in res['relaxed']], data_as_of=data_as_of)
    out['trust'] = {'fit': res['trust']['fit'], 'sufficiency': res['trust']['sufficiency']}
    out['hold_reasons'] = hold
    out['floor'] = {'listing_floor_type': floor_type, 'listing_floor_source': floor_source,
                    'comparable_floor_known': usage != '단독다가구',
                    'rule': ('Q75x%.2f 초과일 때만 UPPER_RANGE, UPPER_TAIL 금지' % (1 + POLICY['detached_shift'])) if usage == '단독다가구' else None}
    out['warning_texts'] = {w: WARNING_TEXT[w] for w in warns if w in WARNING_TEXT}
    out['reference'] = _reference(res, stage, pool, gu, q)
    out['confidence_details'] = {'comparability_score': res['trust']['fit'], 'data_sufficiency_score': res['trust']['sufficiency'],
                                 'recent_share_6m': res['trust'].get('recent_share'), 'relative_iqr': res['trust'].get('rel_iqr')}
    out['reason_codes'] = _reason_codes(hold, warns, stage, status)
    out['comparison'] = {'dong': dong, 'gu': gu, 'building_type': usage, 'trace': res['trace']}
    return out


if __name__ == '__main__':
    import json, sys
    pool = load_pool()
    payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')) if len(sys.argv) > 1 else dict(
        district_code='11620', legal_dong_code='1162010100', building_type='APARTMENT', area_m2=59.9, area_basis='EXCLUSIVE',
        deposit_10k_krw=5000, rent_10k_krw=120, built_year=2005, floor=7)
    print(json.dumps(analyze_listing(payload, pool), ensure_ascii=False, indent=2))
