"""Display existing analyst facts without changing stored analysis or rent policy."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

LABELS = {'COMPARED': '비교 완료', 'REFERENCE_ONLY': '참고용 결과',
          'INSUFFICIENT_DATA': '비교자료 부족', 'INPUT_REVIEW_REQUIRED': '입력 정보 확인 필요',
          'OUT_OF_SCOPE': '지원 범위 밖', 'NOT_ANALYZED': '분석 전'}


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = Decimal(str(value))
        return value if value.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def text_number(value):
    value = abs(value)
    if 0 < value < Decimal('0.01'):
        return '0.01 미만'
    return format(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), ',f').rstrip('0').rstrip('.')


def rent_presentation(result, input_rent, confirmed, valid):
    raw_state = result.get('status') if result else 'NOT_ANALYZED'
    state = raw_state if raw_state in LABELS else 'INPUT_REVIEW_REQUIRED'
    reason_codes = list((result or {}).get('hold_reasons') or (result or {}).get('reason_codes') or [])
    if not confirmed or not valid:
        state = 'INPUT_REVIEW_REQUIRED'
        reason_codes = ['USER_CONFIRMATION_REQUIRED' if not confirmed else 'INPUT_REVIEW_REQUIRED']
    conditions = ((result or {}).get('reference') or {}).get('conditions') or {}
    if state == 'COMPARED' and (conditions.get('scope_code') == 'DISTRICT' or (result or {}).get('stage') == 3):
        # Frontend requirements explicitly prohibit high/low verdicts at district scope.
        # Keep raw analysis untouched; this is a display restriction only.
        state = 'REFERENCE_ONLY'
        reason_codes = list(dict.fromkeys(reason_codes + ['DISTRICT_SCOPE_REFERENCE_ONLY']))
    if state == 'COMPARED' and (result or {}).get('price_label') == 'UNRATED':
        state = 'REFERENCE_ONLY'
    view = {'version': 'RENT_DISPLAY_V1', 'analysis_state': raw_state,
            'state': state, 'status_label': LABELS[state], 'tone': 'NEUTRAL',
            'direction': None, 'headline': LABELS[state], 'can_show_direction': False,
            'input_rent_10k_krw': float(number(input_rent)) if number(input_rent) is not None else None,
            'reference_rent_10k_krw': None, 'middle_50_percent_10k_krw': None,
            'difference_10k_krw': None, 'difference_percent': None,
            'percent_basis': 'COMPARABLE_MEDIAN', 'amount_unit': 'TEN_THOUSAND_KRW',
            'reason_codes': reason_codes,
            'notice': '월세만 비교한 차이입니다. 관리비·별도 공과금은 포함하지 않으며 사기·불법 판정이 아닙니다.'}
    if state not in ('COMPARED', 'REFERENCE_ONLY'):
        return view
    prices = (result or {}).get('prices_10k_krw') or {}
    median, low, high = [number(prices.get(k)) for k in ('median', 'q25', 'q75')]
    diff = number((result or {}).get('rent_difference_10k_krw'))
    ratio = number((result or {}).get('rent_difference_pct'))
    if median is not None and median > 0:
        view['reference_rent_10k_krw'] = float(median)
    if low is not None and high is not None and 0 <= low <= high:
        view['middle_50_percent_10k_krw'] = {'low': float(low), 'high': float(high)}
    if median is None or median <= 0 or diff is None or ratio is None:
        view.update(headline='비교 수치가 없어 차이를 표시할 수 없어요.', reason_codes=reason_codes+['DISPLAY_DATA_INCOMPLETE'])
        return view
    # Preserve source amounts; only convert the contract's ratio to percentage points.
    view.update(difference_10k_krw=float(diff), difference_percent=float(ratio * 100))
    if state == 'REFERENCE_ONLY':
        view['headline'] = '참고 수치예요. 높고 낮음의 판단은 보류해요.'
        return view
    if (diff > 0) != (ratio > 0) or (diff < 0) != (ratio < 0):
        view.update(headline='비교 수치를 다시 확인해야 해요.', reason_codes=reason_codes+['DISPLAY_DATA_INCONSISTENT'])
        return view
    direction, tone, verb = ('HIGHER', 'RED', '높아요') if diff > 0 else ('LOWER', 'BLUE', '낮아요') if diff < 0 else ('SAME', 'NEUTRAL', '같아요')
    view.update(direction=direction, tone=tone, can_show_direction=True,
                headline=f'비교 기준보다 월 {text_number(diff)}만원 · {text_number(ratio * 100)}% {verb}' if diff else '입력한 월세가 비교 기준과 같아요.')
    return view
