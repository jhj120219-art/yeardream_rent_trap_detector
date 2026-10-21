"""Checkbox total grouping. Analyst values are never inferred from an advertised total."""
from decimal import Decimal, InvalidOperation
from .advertised_costs import ITEMS
from .report_money import advertised_money


def grouped_references(options, confirmed, references=None):
    """references is server-side analyst output, not client-supplied option values.

    Its mapping contract is provisional until agreed with the analyst. Each row
    needs low/high KRW and source; no midpoint, OTHER remainder or bills invented.
    Current report calls this with no references until the analyst is connected.
    """
    if options.get('maintenance_input_mode') != 'CHECKBOX_TOTAL_V1':
        return {'state': 'LEGACY_INPUT_REVIEW_REQUIRED', 'selected': None,
                'unselected': None, 'notice': '기존 입력은 체크박스 선택을 다시 확인해야 합니다.'}
    groups = {'selected': [], 'unselected': []}
    refs = references or {}
    for item, (field, _) in ITEMS.items():
        selected = options.get(field) == 'INCLUDED'
        row = {'item': item, 'selected': selected, 'reference_state': 'NO_REFERENCE',
               'reference_low_krw': None, 'reference_high_krw': None, 'source': None}
        ref = refs.get(item)
        if confirmed and isinstance(ref, dict) and ref.get('source'):
            try:
                if isinstance(ref.get('low_krw'), bool) or isinstance(ref.get('high_krw'), bool):
                    raise ValueError('Boolean is not money')
                low, high = Decimal(str(ref['low_krw'])), Decimal(str(ref['high_krw']))
                if not low.is_finite() or not high.is_finite() or not 0 <= low <= high:
                    raise ValueError('Invalid range')
                if low != low.to_integral_value() or high != high.to_integral_value():
                    raise ValueError('KRW must be integer')
                row.update(reference_state='AVAILABLE', reference_low_krw=int(low),
                           reference_high_krw=int(high), source=ref['source'])
            except (KeyError, ValueError, InvalidOperation):
                pass
        groups['selected' if selected else 'unselected'].append(row)

    result = {'version': 'CHECKBOX_TOTAL_V1',
              'state': 'REFERENCE_NOT_CONNECTED' if confirmed else 'NEEDS_USER_CONFIRMATION',
              'advertised_selected_total_10k_krw': advertised_money(options.get('maintenance_10k_krw')),
              'selection_meaning': 'CHECKED_INCLUDED_UNCHECKED_NOT_CONFIRMED',
              'notice': '선택한 항목과 선택하지 않은 항목의 참고 비용을 나눕니다. 미체크는 별도 청구 확정이 아닙니다. 자료 없는 항목은 null이며 기타를 차액으로 만들지 않습니다.'}
    for name, rows in groups.items():
        missing = [r['item'] for r in rows if r['reference_state'] != 'AVAILABLE']
        ready = confirmed and bool(rows) and not missing
        result[name] = {'items': rows, 'state': 'AVAILABLE' if ready else
                        ('NO_ITEMS_SELECTED' if not rows else 'INCOMPLETE'),
                        'missing_items': missing,
                        'reference_low_total_krw': sum(r['reference_low_krw'] for r in rows) if ready else None,
                        'reference_high_total_krw': sum(r['reference_high_krw'] for r in rows) if ready else None}
    if confirmed and references:
        result['state'] = 'AVAILABLE' if all(r['reference_state'] == 'AVAILABLE'
                    for rows in groups.values() for r in rows) else 'PARTIAL_REFERENCE'
    # No cost verdict or percent: statistical meaning and analyst contract are pending.
    return result
