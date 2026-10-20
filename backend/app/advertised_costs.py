"""Advertisement facts only: no estimated costs, totals, or fairness judgments."""
from .report_money import advertised_money

ITEMS = {
    'ELECTRICITY': ('electricity_in_maintenance', 'electricity_10k_krw'),
    'WATER': ('water_in_maintenance', 'water_10k_krw'),
    'GAS': ('gas_in_maintenance', 'gas_10k_krw'),
    'INTERNET': ('internet_status', 'internet_10k_krw'),
    'CLEANING': ('cleaning_in_maintenance', 'cleaning_10k_krw'),
    'COMMON': ('common_in_maintenance', 'common_10k_krw'),
    'OTHER': ('other_in_maintenance', 'other_10k_krw'),
}
STATUSES = {'INCLUDED', 'SEPARATE_CHARGE', 'UNKNOWN'}


def validate_advertised_options(options):
    for status_field, amount_field in ITEMS.values():
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
    return {
        'state': 'USER_CONFIRMED' if confirmed else 'NEEDS_USER_CONFIRMATION',
        'source': 'USER_REVIEWED_ADVERTISEMENT' if confirmed else 'UNCONFIRMED_INPUT',
        'maintenance_10k_krw': advertised_money(options.get('maintenance_10k_krw')),
        'items': [
            {'item': item,
             'status': options.get(status_field) if options.get(status_field) in STATUSES else 'UNKNOWN',
             'quoted_monthly_10k_krw': advertised_money(options.get(amount_field)),
             'label': options.get('other_cost_label') if item == 'OTHER' else None}
            for item, (status_field, amount_field) in ITEMS.items()
        ],
        'note': options.get('maintenance_note'),
        'comparison_state': 'ON_HOLD',
        'notice': '광고에서 확인한 입력값입니다. 미기재 금액은 null이며 예상 비용·적정성 판정·월세 비교 계산에 사용하지 않습니다. 항목 금액의 합계를 관리비에 다시 더하지 않습니다.',
    }
