# -*- coding: utf-8 -*-
"""부분 입력용 파서 — 항목이 일부만 보여도 읽은 항목은 살린다(없는 항목은 None). `ad_cards.py` 의 엄격한 파서는 그대로 두고 따로 둔다.
1) 카드 단위: 월세/전세 머리줄이 있는 카드에서 면적 · 관리비를 각각 찾는다. 없으면 None. `관리비 없음` 은 0.0 (광고가 명시적으로 없다고 쓴 경우만; 전기·수도·가스가 없다는 뜻이 아니다).
   값이 비정상 범위이면 그 항목만 None 으로 비운다(보정하지 않는다). 머리줄(금액)이 비정상이면 카드를 읽지 않는다.
2) 이미지 단위: 카드가 아닌 화면(상세 · 사진)에서도 주소 · 금액 · 면적 · 관리비를 라벨 기준으로 찾는다. 한 값으로 정해지지 않으면(서로 다른 값이 여럿) 읽지 않는다.
카드 튜플 형식: (종류, 보증금_만원, 월세_만원|None, 면적_㎡|None, 관리비_만원|None).  값을 짐작하거나 다른 카드에서 빌려 오지 않는다."""
import re

try:                                   # 백엔드처럼 패키지(machine.analysis_internal.extraction)로 불러올 때와 스크립트로 실행할 때 모두 동작
    from .ad_cards import BAD, HEAD, won
except ImportError:
    from ad_cards import BAD, HEAD, won

AREA = re.compile(r'([\d]+(?:\.\d+)?)\s*[mM㎡][²2]?')
MAINT = re.compile(r'관리비\s*([\d\.]+)\s*만')
MAINT_NONE = re.compile(r'관리비\s*(?:없음|없어요|무료)')
TILE_MARK = '@@TILE@@'
SPLIT = re.compile(r'(?=(?:월세|원세|전세)\s*[\d억])')
# 서울 주소 후보: 시(선택) + 구 + 동/로/길 (+ 번지 · 번길)
ADDR = re.compile(r'(?:서울(?:특별)?시?\s*)?([가-힣]{1,5}구)\s+([가-힣0-9]{1,12}(?:동|로|길)(?:\d+번?길)?)(?:\s*(\d+(?:-\d+)?)(?:번지)?)?')
LABELED = {
    'area_m2': re.compile(r'(?:전용\s*면적|전용)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*[mM㎡][²2]?'),
    'maintenance_10k_krw': re.compile(r'관리비\s*[:：]?\s*(\d+(?:\.\d+)?)\s*만\s*원?'),
}


def _card(kind, dep, rent, blk):
    area = maint = None
    a = AREA.search(blk)
    if a:
        v = float(a.group(1))
        area = v if 3 <= v <= 300 else None
    if MAINT_NONE.search(blk):
        maint = 0.0
    else:
        m = MAINT.search(blk)
        if m:
            try:
                v = float(m.group(1))
            except ValueError:
                v = None
            maint = v if v is not None and v <= 100 else None
    return (kind, dep, rent, area, maint)


def partial_cards(text):
    """다방·직방 목록 카드(월세/전세 머리줄로 시작)를 항목별로 읽는다."""
    out = []
    # 조각(타일) 경계(TILE_MARK)에서 글이 이어 붙지 않게 먼저 나눈다: 잘린 카드 뒤에 다음 조각의 다른 카드 글이 붙어 항목이 섞이는 것을 막는다.
    for part in text.split(TILE_MARK):
        for blk in SPLIT.split(part.replace(chr(10), ' ')):
            h = HEAD.match(blk.strip())
            if not h:
                continue
            dep, rent = won(h.group(2)), won(h.group(3) or '')
            if dep is BAD or rent is BAD or dep is None or dep > 100000 or (rent is not None and rent > 2000):
                continue
            kind = '월세' if h.group(1) == '원세' else h.group(1)
            if kind == '월세' and rent is None:          # 월세 카드는 월세 금액이 있어야 한다(금액 표기가 깨진 머리줄은 읽지 않는다)
                continue
            out.append(_card(kind, dep, rent, blk))
    return out


def normalize_address(m):
    gu, road, num = m.group(1), m.group(2), m.group(3)
    return ' '.join(x for x in ('서울', gu, road, num) if x)


def address_candidates(text):
    """텍스트에서 서울 주소 후보를 모두 찾는다(정규화된 문자열 집합). 첫 번째를 임의로 고르지 않는다."""
    return sorted({normalize_address(m) for m in ADDR.finditer(text.replace(chr(10), ' '))})


def image_fields(text):
    """카드가 아닌 화면에서 라벨 기준으로 읽은 항목. 한 값으로 정해지지 않으면 None."""
    out = {}
    heads = {c[:3] for c in partial_cards(text)}
    if len(heads) == 1:
        kind, dep, rent = next(iter(heads))
        out.update(contract_type=kind, deposit_10k_krw=dep, rent_10k_krw=rent)
    for key, rx in LABELED.items():
        vals = {float(m.group(1)) for m in rx.finditer(text)}
        if len(vals) == 1:
            out[key] = vals.pop()
    cands = address_candidates(text)
    if len(cands) == 1:
        out['address_text'] = cands[0]
    return out


def merge_image_fields(per_engine, min_agree=2):
    """엔진별 image_fields → 항목별 상태. agreed(둘 이상 일치, 자동 입력 후보) / read(한 엔진만) / conflict(엔진끼리 다름) / missing."""
    keys = ('address_text', 'contract_type', 'deposit_10k_krw', 'rent_10k_krw', 'area_m2', 'maintenance_10k_krw')
    res = {}
    for k in keys:
        vals = {e: f[k] for e, f in per_engine.items() if f.get(k) is not None}
        distinct = set(vals.values())
        if not vals:
            res[k] = {'value': None, 'status': 'missing', 'autofill': False}
        elif len(distinct) > 1:
            res[k] = {'value': None, 'status': 'conflict', 'autofill': False, 'candidates': sorted(map(str, distinct))}
        elif len(vals) >= min_agree:
            res[k] = {'value': next(iter(distinct)), 'status': 'agreed', 'autofill': True, 'engines': sorted(vals)}
        else:
            res[k] = {'value': next(iter(distinct)), 'status': 'read', 'autofill': False, 'engines': sorted(vals)}
    if res['address_text']['status'] in ('agreed', 'read'):
        res['address_text']['resolution'] = 'candidate_needs_address_search'   # 주소 검색으로 확인되기 전에는 후보
    return res
