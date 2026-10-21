"""Advertisement facts only: no estimated costs, totals, or fairness judgments."""
from .report_money import advertised_money

ITEMS = {
    'ELECTRICITY': ('electricity_in_maintenance', 'electricity_10k_krw'),
    'WATER': ('water_in_maintenance', 'water_10k_krw'),
    'GAS': ('gas_in_maintenance', 'gas_10k_krw'),
    'INTERNET': ('internet_status', 'internet_10k_krw'),
    'OTHER': ('other_in_maintenance', 'other_10k_krw'),
}
LEGACY_ITEMS = {
    'CLEANING': ('cleaning_in_maintenance', 'cleaning_10k_krw'),
    'COMMON': ('common_in_maintenance', 'common_10k_krw'),
}
STORAGE_ITEMS = {**ITEMS, **LEGACY_ITEMS}
STATUSES = {'INCLUDED', 'SEPARATE_CHARGE', 'UNKNOWN'}


def validate_advertised_options(options):
    for status_field, amount_field in STORAGE_ITEMS.values():
        status = options.get(status_field)
        allowed = STATUSES | ({'AVAILABLE', 'NOT_AVAILABLE'} if status_field == 'internet_status' else set())
        if status is not None and (not isinstance(status,str) or status not in allowed):
            raise ValueError('관리비 항목은 포함·별도 납부·모름 중에서 선택해 주세요.')
        value = options.get(amount_field)
        if value is not None and advertised_money(value) is None:
            raise ValueError('광고에 명시된 항목별 월 금액은 0 이상의 숫자 또는 null이어야 합니다.')
    for field in ('maintenance_note', 'other_cost_label'):
        if options.get(field) is not None and not isinstance(options[field], str):
            raise ValueError('관리비 설명과 기타 항목명은 문자열 또는 null이어야 합니다.')


def advertised_costs(options, confirmed):
    rows = []
    for item, (status_field, amount_field) in ITEMS.items():
        rows.append({'item': item,
            'status': options.get(status_field) if options.get(status_field) in STATUSES else 'UNKNOWN',
            'quoted_monthly_10k_krw': advertised_money(options.get(amount_field)),
            'label': options.get('other_cost_label') if item == 'OTHER' else None})
    legacy = []
    for item, (status_field, amount_field) in LEGACY_ITEMS.items():
        status = options.get(status_field)
        amount = advertised_money(options.get(amount_field))
        if status in ('INCLUDED', 'SEPARATE_CHARGE') or amount is not None:
            legacy.append({'item': item, 'status': status if status in STATUSES else 'UNKNOWN',
                           'quoted_monthly_10k_krw': amount})
    if legacy:
        # Old cleaning/common amounts may overlap with the old OTHER amount.
        # Keep all source details, but do not invent a new subtotal or inclusion.
        original_other = dict(rows[-1])
        rows[-1].update(status='UNKNOWN', quoted_monthly_10k_krw=None, label=None,
            needs_review=True, legacy_components=legacy + [original_other],
            review_reason='LEGACY_OTHER_COMPONENTS_REQUIRE_REVIEW')
    return {
        'category_version': 'FIVE_ITEMS_V1',
        'state': 'USER_CONFIRMED' if confirmed else 'NEEDS_USER_CONFIRMATION',
        'source': 'USER_REVIEWED_ADVERTISEMENT' if confirmed else 'UNCONFIRMED_INPUT',
        'maintenance_10k_krw': advertised_money(options.get('maintenance_10k_krw')),
        'items': rows, 'note': options.get('maintenance_note'),
        'comparison_state': 'ON_HOLD',
        'notice': '광고에 적힌 전기·수도·가스·인터넷·기타 관리비 5항목입니다. 미기재는 null이며 추정·적정성 계산은 보류합니다. 기존 청소·공용·기타 세부내역은 보존하고 중복 여부가 불명확한 금액은 합산하지 않습니다.',
    }
