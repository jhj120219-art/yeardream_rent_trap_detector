"""Call the analyst's existing condition reference function without altering selections.

Only imported inside the isolated analyst subprocess. No tariffs or statistical
policy are implemented here; source conditions and holds remain authoritative.
"""

TYPES = {'electric': 'ELECTRICITY', 'water': 'WATER', 'gas': 'GAS', 'internet': 'INTERNET'}


def all_utility_references(result):
    from machine.analysis_internal.utility.demo.app import month_ref
    conditions = result.get('conditions_used') or {}
    month = conditions.get('target_month')
    if not isinstance(month, int) or isinstance(month, bool) or not 1 <= month <= 12:
        return {'state': 'CONDITIONS_INCOMPLETE', 'items': []}
    gas_ok = conditions.get('gas_user') == '예' and conditions.get('heating_type') == '개별 도시가스'
    values = month_ref(month, conditions.get('housing_type'), conditions.get('household_size'),
                       conditions.get('area_band'), gas_ok)
    items = []
    for key, item in TYPES.items():
        value = values.get(key)
        items.append({'utility_type': item,
                      'estimate_status': 'AVAILABLE' if value is not None else 'HOLD',
                      'reference_low_krw': value['low'] if value is not None else None,
                      'reference_high_krw': value['high'] if value is not None else None,
                      'reference_groups': value['by_view'] if value is not None else [],
                      'hold_reason': None if value is not None else 'ANALYST_CONDITIONS_INCOMPLETE'})
    return {'state': 'COLLECTED', 'method': 'ANALYST_MONTH_REF_SAME_CONDITIONS',
            'conditions_used': dict(conditions), 'items': items,
            'notice': '광고 포함 여부와 독립적인 참고값입니다. 미체크를 별도 청구로 변경하지 않았습니다.'}
