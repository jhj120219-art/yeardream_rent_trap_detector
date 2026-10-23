# -*- coding: utf-8 -*-
"""백엔드 FIVE_ITEMS_V1 광고 관리비 입력(options) -> 머신 표준 광고 구조.

백엔드(backend/app/advertised_costs.py, ADVERTISED_COSTS.md) 계약
- 항목 5개: ELECTRICITY(electricity_in_maintenance, electricity_10k_krw) / WATER / GAS / INTERNET(internet_status, internet_10k_krw) / OTHER(other_in_maintenance, other_10k_krw, other_cost_label)
- 포함 여부: INCLUDED / SEPARATE_CHARGE / UNKNOWN (인터넷은 AVAILABLE / NOT_AVAILABLE 도 가능: 이용 가능 여부일 뿐 포함 여부가 아니다)
- 금액은 만원 단위 숫자(0 이상) 또는 null. 모르면 null, 무료로 명시된 경우에만 0. 총 관리비는 maintenance_10k_krw.
- 예전 청소(cleaning_*)·공용(common_*) 필드는 OTHER 의 설명으로만 보존하고 금액을 합치거나 새로 만들지 않는다.

변환 규칙
- 만원 -> 정수 원은 Decimal 로 한다. 1원 미만이 생기는 값(예: 8.12345만원)은 반올림하지 않고 검증 오류로 알린다.
- null 은 null 로 둔다(0원으로 바꾸지 않음). 문자열 금액("8만원")·음수·무한대·불리언은 검증 오류. 숫자 모양의 문자열("8.5")은 숫자로 읽는다.
- SEPARATE_CHARGE -> SEPARATE. 포함 여부가 UNKNOWN 이면 포함도 별도도 정하지 않는다.
- 별도 납부(SEPARATE) 항목의 금액은 관리비 안의 금액이 아니므로 관리비 항목 금액(advertised_amount_krw)에 넣지 않고 separate_amount_krw 에만 둔다.
- 포함 여부가 UNKNOWN 인데 금액이 적힌 항목은 계산에 쓰지 않고 경고(AMOUNT_WITHOUT_INCLUSION)로 알린다.
- OTHER 는 광고에 명시된 금액만 담는다. 총액에서 다른 항목을 빼서 만들지 않는다.
"""
from decimal import Decimal, InvalidOperation

from .adapter import UTILS

SOURCE_VERSION = 'FIVE_ITEMS_V1'
ITEM_FIELDS = {       # 한글 항목 -> (백엔드 항목명, 상태 필드, 금액 필드)
    '전기': ('ELECTRICITY', 'electricity_in_maintenance', 'electricity_10k_krw'),
    '수도': ('WATER', 'water_in_maintenance', 'water_10k_krw'),
    '가스': ('GAS', 'gas_in_maintenance', 'gas_10k_krw'),
    '인터넷': ('INTERNET', 'internet_status', 'internet_10k_krw'),
}
OTHER_FIELDS = ('other_in_maintenance', 'other_10k_krw')
LEGACY_FIELDS = {'CLEANING': ('cleaning_in_maintenance', 'cleaning_10k_krw', '청소'), 'COMMON': ('common_in_maintenance', 'common_10k_krw', '공용')}
STATUS_MAP = {'INCLUDED': 'INCLUDED', 'SEPARATE_CHARGE': 'SEPARATE', 'SEPARATE': 'SEPARATE', 'UNKNOWN': 'UNKNOWN'}
INTERNET_AVAILABILITY = ('AVAILABLE', 'NOT_AVAILABLE')


def man_to_krw_strict(value):
    """만원 단위 값 -> (정수 원 또는 None, 오류 코드 또는 None). null 은 (None, None)."""
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, 'NOT_A_NUMBER'
    if isinstance(value, str):
        s = value.strip()
        try:
            d = Decimal(s)
        except InvalidOperation:
            return None, 'NOT_A_NUMBER'
    elif isinstance(value, (int, float, Decimal)):
        try:
            d = Decimal(str(value))
        except InvalidOperation:
            return None, 'NOT_A_NUMBER'
    else:
        return None, 'NOT_A_NUMBER'
    if not d.is_finite():
        return None, 'NOT_FINITE'
    if d < 0:
        return None, 'NEGATIVE'
    won = d * 10000
    if won != won.to_integral_value():
        return None, 'FRACTIONAL_WON'
    return int(won), None


def normalize_backend_options(options):
    """FIVE_ITEMS_V1 options -> (표준 광고 구조, 검증 오류 목록). 오류가 있으면 호출한 쪽은 계산하지 않고 오류를 돌려준다."""
    o = options if isinstance(options, dict) else {}
    errors, warnings = [], []
    if options is not None and not isinstance(options, dict):
        errors.append(dict(code='INVALID_INPUT', field='options', message='options 는 객체여야 합니다.'))

    def money(field):
        krw, err = man_to_krw_strict(o.get(field))
        if err:
            errors.append(dict(code='INVALID_AMOUNT', field=field, message=f'{field}: 0 이상의 숫자(만원)이거나 null 이어야 합니다 ({err}).'))
        return krw

    total = money('maintenance_10k_krw')
    items, availability = {}, None
    any_status = False
    for name, (en, status_field, amount_field) in ITEM_FIELDS.items():
        raw = o.get(status_field)
        status = 'UNKNOWN'
        if raw is not None:
            if not isinstance(raw, str) or (raw not in STATUS_MAP and not (en == 'INTERNET' and raw in INTERNET_AVAILABILITY)):
                errors.append(dict(code='INVALID_STATUS', field=status_field, message=f'{status_field}: INCLUDED / SEPARATE_CHARGE / UNKNOWN 중 하나여야 합니다.'))
            elif raw in STATUS_MAP:
                status = STATUS_MAP[raw]
            else:
                availability = raw                                  # 인터넷 AVAILABLE / NOT_AVAILABLE: 포함 여부는 UNKNOWN 으로 둔다
        amount = money(amount_field)
        any_status = any_status or status != 'UNKNOWN'
        item = dict(inclusion=status, billing_basis='UNKNOWN', metering='UNKNOWN', advertised_amount_krw=None, source='BACKEND', user_confirmed=False)
        if amount is not None:
            if status == 'INCLUDED':
                item.update(advertised_amount_krw=amount, billing_basis='FIXED')
            elif status == 'SEPARATE':
                item['separate_amount_krw'] = amount                 # 관리비 안의 금액이 아니다
            else:
                warnings.append(dict(code='AMOUNT_WITHOUT_INCLUSION', field=amount_field, message=f'{amount_field}: 포함 여부를 모르는 항목의 금액은 계산에 쓰지 않습니다.'))
                item['unused_amount_krw'] = amount
        items[name] = item
    # OTHER: 광고에 명시된 값만. 청소·공용(예전 필드)은 설명으로만 보존
    other_status_raw = o.get(OTHER_FIELDS[0])
    if other_status_raw is not None and other_status_raw not in STATUS_MAP:
        errors.append(dict(code='INVALID_STATUS', field=OTHER_FIELDS[0], message=f'{OTHER_FIELDS[0]}: INCLUDED / SEPARATE_CHARGE / UNKNOWN 중 하나여야 합니다.'))
    other_amount = money(OTHER_FIELDS[1])
    labels = []
    lab = o.get('other_cost_label')
    if lab is not None and not isinstance(lab, str):
        errors.append(dict(code='INVALID_INPUT', field='other_cost_label', message='other_cost_label 은 문자열 또는 null 이어야 합니다.'))
    elif lab:
        labels.append(lab.strip())
    legacy = []
    for key, (sf, af, ko) in LEGACY_FIELDS.items():
        st, am = o.get(sf), money(af)
        if st in ('INCLUDED', 'SEPARATE_CHARGE') or am is not None:
            legacy.append(dict(item=key, label=ko, status=STATUS_MAP.get(st, 'UNKNOWN'), advertised_amount_krw=am))
            labels.append(ko)
    if legacy:
        warnings.append(dict(code='LEGACY_OTHER_COMPONENTS', field='cleaning/common', message='예전 청소·공용 세부내역은 기타의 설명으로만 보존하고 금액을 합치지 않습니다.'))
    other = dict(inclusion=STATUS_MAP.get(other_status_raw, 'UNKNOWN'), advertised_amount_krw=other_amount,
                 amount_source='ADVERTISED' if other_amount is not None else 'NOT_PROVIDED',
                 descriptions=[x for x in dict.fromkeys(labels)], legacy_components=legacy,
                 note='기타는 광고에 명시된 금액만 표시하며 총액에서 다른 항목을 빼서 만들지 않습니다.')
    ad = dict(maintenance_total_krw=total, mode='불명', undisclosed=False, parse_incomplete=False, incomplete_reasons=[], conflicts=[],
              items=items, other=other, internet_availability=availability, other_included=[], other_amounts_krw={},
              explicit_inclusion_list=any_status or other['inclusion'] != 'UNKNOWN', notes=[o['maintenance_note']] if isinstance(o.get('maintenance_note'), str) else [],
              source='BACKEND_FIVE_ITEMS_V1', input_warnings=warnings)
    return ad, errors
