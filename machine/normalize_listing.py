#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""입력 변환 계층(adapter): 주소 입력·광고 이미지 AI 추출 결과(계약 v1.1 또는 준비팩 형식)를 analyze_listing 입력으로 변환한다.

  normalize_listing(raw)         -> {'ok', 'payload', 'issues', 'options', 'notes'}
  analyze_raw(raw, pool)         -> normalize 후 analyze_listing 호출. 입력 문제가 있으면 INPUT_REVIEW_REQUIRED 로 반환
  classify_floor_text(text)      -> 광고 층 문구를 floor/total_floors/floor_type 으로 분류(AI 출력 교차 검증·대체용)

원칙
 - 사용자가 확인하지 않은 값(user_confirmed != true)은 가격 판정에 쓰지 않는다.
 - AI가 읽은 층(IMAGE_EXTRACTED)은 사용자 확인 전까지 판정 근거가 아니다. 단독다가구 조건부 판정에는 floor_type 이 USER_CONFIRMED 여야 한다.
 - floor == 0 은 '미확인'(None). 법정동·자치구 코드는 문자열 유지(앞자리 0 보존). 금액은 만원, 면적은 ㎡.
 - 관리비·인터넷·엘리베이터·주차 등 옵션은 시세 판정과 분리해 options 로 돌려준다.
"""
from __future__ import annotations
import re

BUILDING_ALIAS = {
    'APARTMENT': 'APARTMENT', 'MULTI_UNIT': 'MULTI_UNIT', 'OFFICETEL': 'OFFICETEL',
    'DETACHED_MULTI': 'DETACHED_MULTI', 'SINGLE_MULTI_HOUSEHOLD': 'DETACHED_MULTI',
    '아파트': 'APARTMENT', '연립다세대': 'MULTI_UNIT', '다세대': 'MULTI_UNIT', '연립': 'MULTI_UNIT', '빌라': None,   # 빌라는 모호 -> 확인 필요
    '오피스텔': 'OFFICETEL', '단독다가구': 'DETACHED_MULTI', '다가구': 'DETACHED_MULTI', '단독': 'DETACHED_MULTI',
}
AREA_BASIS = {'EXCLUSIVE', 'SUPPLY', 'CONTRACT', 'RENTAL_REPORTED', 'UNKNOWN'}
FLOOR_TYPES = {'GROUND', 'BASEMENT', 'UNKNOWN'}
FLOOR_SOURCES = {'USER_CONFIRMED', 'IMAGE_EXTRACTED', 'UNKNOWN'}

# ------------------------------------------------------------------ 층 문구 분류
_BASE = re.compile(r'반\s*지하|지하\s*\d*\s*층|지\s*층|B\s*1|B1|지하\s*\d*\s*호')
_BASE_PARK = re.compile(r'지하\s*주차')
_RATIO = re.compile(r'(\d+)\s*층\s*(?:중|/|건물\s*중)\s*(\d+)\s*층')
_TOTAL = re.compile(r'(?:건물\s*)?(?:총|전체)\s*(\d+)\s*층|(\d+)\s*층\s*건물')
_SINGLE = re.compile(r'(?<![\d지])(\d+)\s*층')


def classify_floor_text(text: str | None) -> dict:
    """광고 층 문구 -> {'floor','total_floors','floor_type','review_required','reason'}.
    floor_type 은 '문구가 말하는 것'일 뿐 사용자 확인 전에는 판정 근거로 쓰지 않는다."""
    out = dict(floor=None, total_floors=None, floor_type='UNKNOWN', review_required=True, reason='UNCLEAR')
    if not text or not str(text).strip():
        out['reason'] = 'NO_FLOOR_INFO'
        return out
    s = str(text)
    nums = [int(x) for x in re.findall(r'(\d+)\s*층', s)]
    if len(re.findall(r'(?:매물|호실|원룸)[^,/·]*', s)) >= 2 and len(set(nums)) >= 2 and re.search(r'동시|·|/|,', s) and not _RATIO.search(s):
        out['reason'] = 'MULTIPLE_LISTINGS'
        return out
    s_nopark = _BASE_PARK.sub(' ', s)                       # 지하주차장은 주거 매물의 지하층 증거가 아님
    m_base = _BASE.search(s_nopark)
    m_ratio = _RATIO.search(s)
    if m_base:
        out.update(floor=-1, floor_type='BASEMENT', review_required=False, reason='BASEMENT_TEXT')
        if _SINGLE.search(s_nopark) and re.search(r'(?<![지\d])1\s*층', s_nopark) and re.search(r'반\s*지하', s_nopark):
            out.update(review_required=True, reason='CONTRADICTION_GROUND_AND_BASEMENT')     # 1층이라고 적었지만 실제 반지하
        return out
    if m_ratio:
        total, flo = int(m_ratio.group(1)), int(m_ratio.group(2))
        if 1 <= flo <= total:
            out.update(floor=flo, total_floors=total, floor_type='GROUND', review_required=False, reason='FLOOR_OF_TOTAL')
        else:
            out.update(total_floors=total, reason='INCONSISTENT_FLOOR')
        return out
    if re.search(r'저\s*층', s):
        out['reason'] = 'LOW_FLOOR_AMBIGUOUS'
        return out
    m_total = _TOTAL.search(s)
    if m_total:
        out.update(total_floors=int(m_total.group(1) or m_total.group(2)), reason='TOTAL_FLOORS_ONLY')
        return out
    m = _SINGLE.search(s)
    if m:
        n = int(m.group(1))
        if re.search(r'매물|원룸|호실|해당', s):
            out.update(floor=n, floor_type='GROUND', review_required=False, reason='LISTING_FLOOR')
        else:
            out['reason'] = 'SINGLE_FLOOR_AMBIGUOUS'      # '4층'만 있으면 건물 층수인지 호실 층수인지 알 수 없음
        return out
    if re.search(r'지하\s*주차', s):
        out['reason'] = 'PARKING_BASEMENT_ONLY'
        return out
    out['reason'] = 'NO_FLOOR_INFO'
    return out


# ------------------------------------------------------------------ 변환
def _num(x):
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = re.sub(r'[,\s만원㎡]', '', str(x))
    try:
        return float(s)
    except ValueError:
        return None


def _flatten(raw: dict):
    """계약 v1.1(listing/options/confirmation) 또는 준비팩 평면 형식 -> (listing, options, confirmation)"""
    if isinstance(raw.get('listing'), dict):
        return dict(raw['listing']), dict(raw.get('options') or {}), dict(raw.get('confirmation') or {})
    flat = dict(raw)
    options = {k: flat.pop(k) for k in list(flat) if k in ('maintenance_10k_krw', 'internet_status', 'elevator_status', 'parking_status',
                                                              'electricity_in_maintenance', 'gas_in_maintenance', 'water_in_maintenance')}
    conf = {'user_confirmed': flat.pop('user_confirmed', None), 'input_source': flat.pop('input_source', None),
            'confirmed_fields': flat.pop('confirmed_fields', None) or []}
    return flat, options, conf


def normalize_listing(raw: dict) -> dict:
    issues, notes = [], []
    listing, options, conf = _flatten(dict(raw or {}))
    confirmed = set(conf.get('confirmed_fields') or [])
    # --- 사용자 확인
    if conf.get('user_confirmed') is not True:
        issues.append('USER_CONFIRMATION_REQUIRED')
    # --- 지역
    district = listing.get('district_code')
    district = None if district in (None, '') else str(district).strip()
    if not district or not re.fullmatch(r'\d{5}', district):
        issues.append('ADDRESS_REVIEW_REQUIRED'); notes.append('district_code 는 5자리 문자열이어야 합니다(예: "11620").')
    ldc = listing.get('legal_dong_code')
    ldc = None if ldc in (None, '') else str(ldc).strip()
    if ldc and not re.fullmatch(r'\d{10}', ldc):
        issues.append('ADDRESS_REVIEW_REQUIRED'); notes.append('legal_dong_code 는 10자리 문자열이어야 합니다.')
    dong = listing.get('dong') or listing.get('legal_dong_name')
    if not ldc and not dong:
        issues.append('ADDRESS_REVIEW_REQUIRED')
    if listing.get('requires_address_confirmation'):
        issues.append('ADDRESS_REVIEW_REQUIRED')
    # --- 주택 유형
    btype_in = str(listing.get('building_type') or '').strip()
    btype = BUILDING_ALIAS.get(btype_in) if btype_in else None
    if btype is None:
        issues.append('BUILDING_TYPE_REVIEW_REQUIRED')
        if btype_in and btype_in not in BUILDING_ALIAS:
            notes.append('알 수 없는 building_type: %s' % btype_in)
    # --- 금액·면적
    dep, rent = _num(listing.get('deposit_10k_krw')), _num(listing.get('rent_10k_krw'))
    if dep is None or dep < 0:
        issues.append('DEPOSIT_REVIEW_REQUIRED')
    if rent is None or rent <= 0:
        issues.append('RENT_REVIEW_REQUIRED')
    area = _num(listing.get('area_m2'))
    if area is None or area <= 0:
        issues.append('AREA_REVIEW_REQUIRED')
    basis = str(listing.get('area_basis') or 'UNKNOWN').upper()
    if basis not in AREA_BASIS:
        issues.append('AREA_REVIEW_REQUIRED'); basis = 'UNKNOWN'
    # --- 건축연도
    built = _num(listing.get('built_year'))
    # --- 층: 0 은 미확인, 사용자 확인이 없는 층 유형은 판정에 쓰지 않는다
    floor = _num(listing.get('floor'))
    if floor == 0:
        floor = None; notes.append('floor=0 은 층 미확인으로 처리했습니다.')
    ftype = str(listing.get('floor_type') or 'UNKNOWN').upper()
    fsrc = str(listing.get('floor_source') or 'UNKNOWN').upper()
    if ftype not in FLOOR_TYPES:
        ftype = 'UNKNOWN'
    if fsrc not in FLOOR_SOURCES:
        fsrc = 'UNKNOWN'
    floor_trusted = (fsrc == 'USER_CONFIRMED') or ('floor_type' in confirmed) or ('floor' in confirmed and ftype != 'UNKNOWN')
    if not floor_trusted:
        if ftype != 'UNKNOWN' or floor is not None:
            notes.append('층 정보가 사용자 확인 전(IMAGE_EXTRACTED)이라 가격 판정에는 사용하지 않습니다(층 미확인으로 처리).')
        ftype, floor = 'UNKNOWN', None
    elif ftype == 'UNKNOWN' and floor is not None:
        ftype = 'GROUND' if floor >= 1 else 'BASEMENT'
    # --- 변환 결과
    payload = {'district_code': district, 'building_type': btype, 'area_m2': area, 'area_basis': basis,
               'deposit_10k_krw': dep, 'rent_10k_krw': rent}
    if ldc:
        payload['legal_dong_code'] = ldc
    elif dong:
        payload['dong'] = str(dong).strip()
    if built is not None:
        payload['built_year'] = int(built)
    if floor is not None:
        payload['floor'] = int(floor)
    if ftype in ('GROUND', 'BASEMENT'):
        payload['floor_type'] = ftype
        payload['floor_source'] = 'USER_CONFIRMED'
    for k in ('as_of',):
        if listing.get(k):
            payload[k] = listing[k]
    issues = sorted(set(issues))
    return {'ok': not issues, 'payload': payload, 'issues': issues, 'options': options, 'notes': notes,
            'floor_final': {'floor': payload.get('floor'), 'floor_type': ftype, 'floor_trusted': floor_trusted}}


def analyze_raw(raw: dict, pool):
    """normalize + analyze. 입력 문제가 있으면 분석하지 않고 INPUT_REVIEW_REQUIRED 로 돌려준다."""
    import analyze as an
    n = normalize_listing(raw)
    if not n['ok']:
        res = an._base_result('INPUT_REVIEW_REQUIRED', errors=n['issues'], messages=n['notes'],
                              data_as_of=str(__import__('pandas').Timestamp(pool.max_date).date()))
        res['input_issues'] = n['issues']
        return res
    res = an.analyze_listing(n['payload'], pool)
    res['input_notes'] = n['notes']
    res['options'] = n['options']                          # 시세 판정과 분리된 옵션 정보(매물 간 비교용으로 전달)
    return res
