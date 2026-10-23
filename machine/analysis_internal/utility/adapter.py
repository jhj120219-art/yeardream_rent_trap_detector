# -*- coding: utf-8 -*-
"""광고 판독 결과(parse_detail 등) -> 관리비 점검 입력으로 바꾸는 변환 단계.

설계 원칙 (ChatGPT 상의 2026-10-20 반영)
- 금액은 정수 원(KRW) 단위로 통일한다. 만원 표기는 Decimal 로 변환하고 float 을 쓰지 않는다. 총액이 없으면 None 이며 0원으로 바꾸지 않는다(명시된 0원은 0).
- 항목마다 세 가지를 따로 둔다: inclusion(INCLUDED / SEPARATE / UNKNOWN), billing_basis(FIXED / ACTUAL / MIXED / UNKNOWN), metering(INDIVIDUAL / SHARED / UNKNOWN).
  * '실비'는 부과 방식일 뿐 개별 계량의 증거가 아니다 -> 광고만으로는 metering 은 항상 UNKNOWN. 사용자가 확인해야 바뀐다.
  * SEPARATE 와 UNKNOWN 을 섞지 않는다. 광고에 안 적힌 항목은 UNKNOWN 이다.
- 광고 읽기가 불완전(incomplete)해도 사용자가 해당 값을 직접 확인하면 최종 입력은 '확인 완료'가 될 수 있다(원본 추출 기록은 그대로 남김).
- 같은 항목이 포함과 별도로 동시에 읽히면 충돌로 표시하고 어느 쪽도 고르지 않는다.
"""
import re
from decimal import Decimal, InvalidOperation

UTILS = ('수도', '전기', '가스', '인터넷')
UTIL_KEY = {'수도': 'water', '전기': 'electric', '가스': 'gas', '인터넷': 'internet'}
INCLUSION = ('INCLUDED', 'SEPARATE', 'UNKNOWN')
BASIS = ('FIXED', 'ACTUAL', 'MIXED', 'UNKNOWN')
METERING = ('INDIVIDUAL', 'SHARED', 'UNKNOWN')
MAX_PLAUSIBLE_TOTAL_KRW = 5_000_000     # 월 관리비로 보기 어려운 금액(단위 혼동 의심). demo 의 상한과 같다.

_UNITS = {'억': Decimal(10) ** 8, '만': Decimal(10) ** 4, '천': Decimal(10) ** 3, '백': Decimal(100)}


def parse_krw(text):
    """금액 문구 -> 정수 원. 해석할 수 없으면 None(추정하지 않는다).
    예: '8만원' 80000, '8.5만원' 85000, '8만 5천원' 85000, '80,000원' 80000, '0원' 0, '없음' None."""
    if text is None:
        return None
    if isinstance(text, bool):
        return None
    if isinstance(text, int):
        return text
    s = str(text).strip().replace(',', '').replace(' ', '')
    if not s:
        return None
    if re.fullmatch(r'0+원?', s):
        return 0
    s = s[:-1] if s.endswith('원') else s
    # 한글 단위가 섞인 표기: 8만5천 / 8.5만 / 1억2천만
    if re.search(r'[억만천백]', s):
        total, rest = Decimal(0), s
        for m in re.finditer(r'(\d+(?:\.\d+)?)([억만천백])', s):
            total += Decimal(m.group(1)) * _UNITS[m.group(2)]
            rest = rest.replace(m.group(0), '', 1)
        if rest and re.fullmatch(r'\d+', rest):          # '8만5000' 처럼 끝에 숫자가 남는 경우
            total += Decimal(rest)
            rest = ''
        return int(total.to_integral_value()) if not rest else None
    try:
        v = Decimal(s)
    except InvalidOperation:
        return None
    if v < 0 or v != v.to_integral_value():
        return None
    return int(v)


def man_to_krw(man):
    """만원 단위 숫자(입력 필드) -> 정수 원. 8.5 -> 85000."""
    if man in (None, ''):
        return None
    try:
        return int((Decimal(str(man)) * 10000).to_integral_value())
    except InvalidOperation:
        return None


def krw_to_man(krw):
    return None if krw is None else float(Decimal(krw) / 10000)


def _item(inclusion='UNKNOWN', basis='UNKNOWN', amount=None, source='AD'):
    return dict(inclusion=inclusion, billing_basis=basis, metering='UNKNOWN', advertised_amount_krw=amount, source=source, user_confirmed=False)


def normalize_ad(extraction):
    """parse_detail 출력(또는 같은 키를 가진 dict) -> 표준 광고 구조.
    입력 키: total(원) / maintenance_total_krw, mode, included, excluded_items, amounts{항목: 원}, actual_items, not_provided,
    utility_included, utility_separate, incomplete, undisclosed. 값은 모두 '원' 단위여야 하며, 만원 값이 섞이면 호출한 쪽이 먼저 바꿔야 한다."""
    e = extraction or {}
    total = e.get('maintenance_total_krw', e.get('total'))
    total = parse_krw(total) if not isinstance(total, int) else total
    inc = set(e.get('utility_included') or [])
    sep = set(e.get('utility_separate') or [])
    amounts = {k: v for k, v in (e.get('amounts') or {}).items() if isinstance(v, int)}
    actual_items = set(e.get('actual_items') or [])
    mode = e.get('mode') or '불명'
    items, conflicts = {}, []
    for u in UTILS:
        inclusion = 'INCLUDED' if u in inc else ('SEPARATE' if u in sep else 'UNKNOWN')
        if u in inc and u in sep:
            conflicts.append(u)
            inclusion = 'UNKNOWN'                          # 충돌한 항목은 어느 쪽도 고르지 않는다
        amt = amounts.get(u)
        if u in actual_items:
            basis = 'ACTUAL'
        elif amt is not None:
            basis = 'FIXED'
        elif inclusion == 'INCLUDED':
            basis = {'정액': 'FIXED', '실비': 'ACTUAL', '혼합': 'MIXED'}.get(mode, 'UNKNOWN')
        else:
            basis = 'UNKNOWN'
        items[u] = _item(inclusion, basis, amt)
    known = [k for k in (e.get('included') or []) if k not in UTILS]
    other_included = [k for k in known if k not in ('공용 관리비', '일반(공용) 관리비', 'TV', '난방', '기타 관리비')]
    reasons = list(e.get('incomplete') or [])
    return dict(
        maintenance_total_krw=total, mode=mode, undisclosed=bool(e.get('undisclosed')),
        parse_incomplete=bool(reasons), incomplete_reasons=reasons, conflicts=conflicts,
        items=items, other_included=other_included, other_amounts_krw={k: v for k, v in amounts.items() if k not in UTILS},
        explicit_inclusion_list=bool(inc or sep or e.get('included') or e.get('excluded_items')),
        notes=list(e.get('notes') or []))


def apply_user_confirmation(ad, user):
    """사용자가 확인·수정한 값을 광고 구조에 덮어쓴다. 읽기 불완전(incomplete)은 사용자가 총액과 항목을 확인했다고 표시한 경우에만 해소된다.
    user: {confirmed(bool), maintenance_total_krw 또는 maintenance_total_man, resolves_incomplete(bool),
           items: {'수도': {inclusion, billing_basis, metering, amount_krw}}, metering(전체 기본값)}"""
    ad = dict(ad)
    ad['items'] = {k: dict(v) for k, v in ad['items'].items()}
    u = user or {}
    if u.get('maintenance_total_krw') is not None or u.get('maintenance_total_man') is not None:
        ad['maintenance_total_krw'] = parse_krw(u['maintenance_total_krw']) if u.get('maintenance_total_krw') is not None else man_to_krw(u['maintenance_total_man'])
        ad['total_source'] = 'USER'
    default_metering = u.get('metering')
    for name, patch in (u.get('items') or {}).items():
        if name not in ad['items']:
            continue
        it = ad['items'][name]
        for field, allowed in (('inclusion', INCLUSION), ('billing_basis', BASIS), ('metering', METERING)):
            if patch.get(field) in allowed:
                it[field] = patch[field]
        if 'amount_krw' in patch:
            it['advertised_amount_krw'] = parse_krw(patch['amount_krw'])
        it['source'], it['user_confirmed'] = 'USER', True
    if default_metering in METERING:
        for it in ad['items'].values():
            if it['inclusion'] == 'INCLUDED' and it['metering'] == 'UNKNOWN':
                it['metering'] = default_metering
                it['user_confirmed'] = True
    ad['conflicts'] = [n for n in ad['conflicts'] if not ad['items'][n]['user_confirmed']]
    ad['user_confirmed'] = bool(u.get('confirmed'))
    if u.get('resolves_incomplete') and ad['user_confirmed']:
        ad['incomplete_resolved_by_user'] = True
    ad['parse_incomplete_unresolved'] = ad['parse_incomplete'] and not ad.get('incomplete_resolved_by_user', False)
    return ad


def to_demo_params(ad, cond):
    """표준 광고 구조 + 사용자 조건 -> demo.app.estimate() 입력. 모르는 조건은 None 으로 넘겨 그 관점을 건너뛰게 한다(임의 가정 없음).
    cond: {target_month, household_size, housing_type, area_m2 | area_band, heating_type, gas_user}"""
    c = cond or {}
    inc = [n for n in UTILS if ad['items'][n]['inclusion'] == 'INCLUDED']
    sep = [n for n in UTILS if ad['items'][n]['inclusion'] == 'SEPARATE']
    itemized = {n: ad['items'][n]['advertised_amount_krw'] for n in inc if ad['items'][n]['advertised_amount_krw'] is not None}
    mets = {ad['items'][n]['metering'] for n in inc}
    metering = '세대별' if mets == {'INDIVIDUAL'} else ('공동' if 'SHARED' in mets else '모름')
    total = ad.get('maintenance_total_krw')
    return dict(month=c.get('target_month') or 1, household=c.get('household_size'), housing=c.get('housing_type'),
                area_band=c.get('area_band') or area_band_of(c.get('area_m2')), heating=c.get('heating_type') or '모름',
                gas_user=c.get('gas_user') or '모름', metering=metering,
                mgmt_man=None if total is None else krw_to_man(total), included=inc, excluded=sep, itemized=itemized)


def area_band_of(area_m2):
    if area_m2 in (None, ''):
        return None
    a = float(area_m2)
    return '~33㎡' if a < 33 else ('33~66㎡' if a < 66 else ('66~99㎡' if a < 99 else None))   # 99㎡ 이상은 지원 밖 -> 면적 관점을 건너뜀
