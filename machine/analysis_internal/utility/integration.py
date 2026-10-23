# -*- coding: utf-8 -*-
"""run_maintenance(payload) — 광고 판독 결과 + 사용자 확인 + 사용자 조건 -> 관리비 점검 결과 JSON 하나.

흐름: ① 광고 추출(ad / ad_text) -> ② 표준화(adapter.normalize_ad) -> ③ 사용자 확인 반영(adapter.apply_user_confirmation)
      -> ④ 계산(demo.app.estimate: 항목별 참고 비용 + 관리비 구성 보기) -> ⑤ 결과 JSON(maintenance.v1)

원칙: 판정하지 않는다. status 는 REFERENCE_ONLY / REVIEW_REQUIRED / INSUFFICIENT_DATA 뿐이고, 모든 금액은 '참고 추정값'이다.
- REVIEW_REQUIRED 는 "광고에서 읽은 정보나 입력값을 확인해야 한다"는 뜻으로만 쓴다. 광고 금액이 참고 구간보다 크다는 이유로 상태를 올리지 않고,
  차이는 상태와 별개인 reference_comparison 에 사실(광고 금액, 참고 구간, 비율, 한계)만 적는다.
- 모르는 조건을 임의로 가정하지 않는다(그 관점을 건너뛰고 missing_fields 와 확인 질문으로 알린다).
- 기타(OTHER)는 광고에 명시된 금액만 담는다. 총액에서 다른 항목을 빼서 기타 금액을 만들지 않는다(백엔드 FIVE_ITEMS_V1 규칙).
  예전의 '참고 가정에 따른 나머지 금액'(구성 보기)은 기본으로 끄고 experimental_remainder=True 일 때만 내부 실험용으로 계산한다.
- 광고에 금액이 적힌 항목은 그 금액만 쓰고 추정값을 다시 더하거나 빼지 않는다. 별도 실비 항목은 관리비 안의 합계에 넣지 않는다.
- 오류 구분: 입력 검증 오류(INVALID_INPUT / INVALID_AMOUNT / INVALID_STATUS / UNSUPPORTED_CONTRACT_VERSION)와 서버 환경 오류(MISSING_DATA_FILE)는
  errors 에 담고, 사용자가 정보를 덜 입력한 경우(INSUFFICIENT_DATA)와 구분한다.

payload 예:
{ "request_id": "r1",
  "backend_options": <백엔드 FIVE_ITEMS_V1 options: maintenance_10k_krw, electricity_in_maintenance, electricity_10k_krw, ... other_cost_label>,
  "contract_version": "FIVE_ITEMS_V1",            # backend_options 일 때 (생략 가능)
  "ad": <parse_detail 출력 또는 같은 키의 dict>   # 또는 "ad_text": "<상세보기 글자>"  (backend_options 가 없을 때)
  "user": {"confirmed": true, "resolves_incomplete": false, "maintenance_total_man": 8, "metering": "INDIVIDUAL",
           "items": {"수도": {"inclusion": "INCLUDED", "billing_basis": "FIXED", "metering": "INDIVIDUAL", "amount_krw": 20000}}},
  "conditions": {"target_month": 10, "household_size": 1, "housing_type": "다세대·연립", "area_m2": 20, "heating_type": "모름", "gas_user": "모름"} }
"""
import sys
from pathlib import Path

from . import adapter as A
from . import backend_options as BO
from .data_files import MissingDataFile
from .tariffs import ELECTRIC, GAS

SCHEMA_VERSION = 'maintenance.v1'
CALCULATION_VERSION = 'utility-v0.2'
SUPPORTED_CONTRACTS = (None, 'FIVE_ITEMS_V1', 'AD_EXTRACTION_V1')      # None = 생략(입력 종류로 판단)
STATUSES = ('REFERENCE_ONLY', 'REVIEW_REQUIRED', 'INSUFFICIENT_DATA')
TYPE_NAME = {'water': 'WATER', 'electric': 'ELECTRICITY', 'gas': 'GAS', 'internet': 'INTERNET'}
HOUSING_TYPES = ('단독·다가구', '다세대·연립', '아파트', '오피스텔')
HEATING_TYPES = ('개별 도시가스', '지역난방', '중앙난방', '전기', '모름')
NEVER = ['총액-추정합계를 부당 청구액으로 해석하지 않음', '참고 범위를 정상 범위로 해석하지 않음', '개별 가구 실제 청구액 예측이 아님']


def _estimate(params):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))        # analysis_internal (demo.app 이 utility 를 절대 경로로 불러옴)
    from .demo.app import estimate
    return estimate(params)


def _clean_conditions(cond):
    c = dict(cond or {})
    out = dict(target_month=None, household_size=None, housing_type=None, area_band=None, heating_type='모름', gas_user='모름')
    m = c.get('target_month')
    out['target_month'] = int(m) if isinstance(m, (int, float, str)) and str(m).isdigit() and 1 <= int(m) <= 12 else None
    h = c.get('household_size')
    out['household_size'] = int(h) if isinstance(h, (int, float, str)) and str(h).isdigit() and int(h) >= 1 else None
    out['housing_type'] = c.get('housing_type') if c.get('housing_type') in HOUSING_TYPES else None
    out['area_band'] = c.get('area_band') or A.area_band_of(c.get('area_m2'))
    out['heating_type'] = c.get('heating_type') if c.get('heating_type') in HEATING_TYPES else '모름'
    out['gas_user'] = c.get('gas_user') if c.get('gas_user') in ('예', '아니오') else '모름'
    return out


def _missing_and_questions(ad, cond, included):
    miss, q = [], []
    if ad.get('maintenance_total_krw') is None:
        miss.append('maintenance_total'); q.append('광고에 적힌 관리비 총액(월, 원 또는 만원 단위)을 확인해 주세요.')
    if not ad['explicit_inclusion_list'] and not any(i['inclusion'] != 'UNKNOWN' for i in ad['items'].values()):
        miss.append('utilities.inclusion'); q.append('관리비에 포함되는 항목(전기·수도·가스·인터넷 등)과 별도로 내는 항목을 확인해 주세요.')
    for n in A.UTILS:
        if ad['items'][n]['inclusion'] == 'INCLUDED' and ad['items'][n]['metering'] == 'UNKNOWN':
            miss.append(f'utilities.{A.UTIL_KEY[n]}.metering')
    if any(ad['items'][n]['metering'] == 'UNKNOWN' for n in included):
        q.append('포함된 전기·수도·가스는 세대별 계량기로 사용량만큼 정산하나요, 건물 전체 요금을 나누거나 정액인가요?')
    if cond['household_size'] is None:
        miss.append('household_size'); q.append('거주 가구원 수를 알려 주세요.')
    if cond['housing_type'] is None:
        miss.append('housing_type'); q.append('주택 유형(단독·다가구 / 다세대·연립 / 아파트 / 오피스텔)을 알려 주세요.')
    if cond['area_band'] is None:
        miss.append('area'); q.append('전용면적(㎡)을 알려 주세요. 99㎡ 이상은 현재 면적 기준 참고값이 없습니다.')
    if '가스' in included and (cond['heating_type'] == '모름' or cond['gas_user'] == '모름'):
        miss.append('heating_type'); q.append('난방·온수가 개별 도시가스인가요, 중앙·지역난방인가요? 가스를 실제로 사용하나요?')
    if cond['target_month'] is None:
        miss.append('target_month'); q.append('어느 달 기준으로 볼까요? (계절에 따라 전기·가스가 크게 달라집니다)')
    return miss, q


def _unverified():
    out = []
    if not ELECTRIC['verified']['climate']:
        out.append('CLIMATE_CHARGE')
    if not ELECTRIC['verified']['fund']:
        out.append('POWER_FUND_RATE')
    if not GAS['verified']['heat']:
        out.append('GAS_CALORIFIC_VALUE')
    return out


def _blocked_result(p, errors, status_reason, source_contract_version=None):
    """입력 검증 오류 등으로 계산하지 않을 때: 같은 모양의 결과에 errors 만 담아 돌려준다(상태는 INSUFFICIENT_DATA)."""
    return dict(
        schema_version=SCHEMA_VERSION, request_id=(p or {}).get('request_id') if isinstance(p, dict) else None, calculation_version=CALCULATION_VERSION,
        source_contract_version=source_contract_version, tariff_version=None,
        status='INSUFFICIENT_DATA', status_reason=status_reason, advertised=None, items=None, conditions_used=None,
        utility_estimates=[], separate_items=[], reference_comparison=[],
        decomposition=dict(enabled=False, status='DISABLED', remainder_low_krw=None, remainder_high_krw=None),
        missing_fields=[], reason_codes=sorted(set(status_reason)), warnings=[], input_warnings=[], confirmation_questions=[],
        assumptions=None, recent_reference=None, errors=errors, never=NEVER)


def run_maintenance(payload):
    p = payload if isinstance(payload, dict) else {}
    if payload is not None and not isinstance(payload, dict):
        return _blocked_result({}, [dict(code='INVALID_INPUT', field='payload', message='payload 는 객체여야 합니다.')], ['INVALID_INPUT'])
    reasons, warnings = [], []
    # ⓪ 계약 버전
    cv = p.get('contract_version')
    if cv not in SUPPORTED_CONTRACTS:
        return _blocked_result(p, [dict(code='UNSUPPORTED_CONTRACT_VERSION', field='contract_version',
                                        message=f'지원하지 않는 계약 버전입니다: {cv!r}. 지원: FIVE_ITEMS_V1(backend_options), AD_EXTRACTION_V1(ad / ad_text)')],
                               ['UNSUPPORTED_CONTRACT_VERSION'], cv)
    # ① 광고 입력: 백엔드 5항목(options) 또는 광고 추출(ad / ad_text)
    input_warnings = []
    if p.get('backend_options') is not None:
        base, verr = BO.normalize_backend_options(p['backend_options'])
        if verr:
            return _blocked_result(p, verr, sorted({e['code'] for e in verr}), 'FIVE_ITEMS_V1')
        input_warnings = base.get('input_warnings', [])
        source_cv = 'FIVE_ITEMS_V1'
    else:
        extraction = p.get('ad')
        if extraction is None and p.get('ad_text'):
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'extraction'))
            from parse_detail import parse_detail
            extraction = parse_detail(str(p['ad_text']))
        base = A.normalize_ad(extraction or {})
        source_cv = 'AD_EXTRACTION_V1'
    # ②③ 사용자 확인
    ad = A.apply_user_confirmation(base, p.get('user'))
    cond = _clean_conditions(p.get('conditions'))
    total = ad.get('maintenance_total_krw')
    if total is not None and (total < 0 or total > A.MAX_PLAUSIBLE_TOTAL_KRW):
        reasons.append('UNIT_OUT_OF_RANGE')
        warnings.append('입력한 관리비가 범위를 벗어났습니다(음수이거나 월 500만원 초과). 원/만원 단위를 확인해 주세요.')
    if ad['conflicts']:
        reasons.append('INCLUSION_CONFLICT')
    if ad.get('parse_incomplete_unresolved'):
        reasons.append('PARSE_INCOMPLETE_UNCONFIRMED')
    included = [n for n in A.UTILS if ad['items'][n]['inclusion'] == 'INCLUDED']
    known = [ad['items'][n]['advertised_amount_krw'] for n in included if ad['items'][n]['advertised_amount_krw'] is not None]
    oth = ad.get('other') or {}
    if oth.get('inclusion') == 'INCLUDED' and oth.get('advertised_amount_krw') is not None:
        known.append(oth['advertised_amount_krw'])
    if total is not None and known and sum(known) > total:      # 광고에 적힌 포함 항목 금액의 합이 총액보다 크다: 어느 쪽이 틀렸는지 알 수 없으니 임의로 고치지 않고 확인을 요청
        reasons.append('ITEM_SUM_EXCEEDS_TOTAL')
        warnings.append(f'광고에 적힌 포함 항목 금액의 합({sum(known):,}원)이 관리비 총액({total:,}원)보다 큽니다. 입력을 확인해 주세요.')
    miss, questions = _missing_and_questions(ad, cond, included)
    # ④ 계산
    params = A.to_demo_params(ad, dict(cond, target_month=cond['target_month']))
    params['month'] = cond['target_month'] or 1
    params['household'] = cond['household_size']
    params['area_band'] = cond['area_band']
    errors = []
    try:
        est = _estimate(params) if (included or ad['items'] and any(i['inclusion'] == 'SEPARATE' for i in ad['items'].values())) else None
    except MissingDataFile as e:     # 필요한 데이터 파일이 없으면 어떤 파일이 없는지와 준비 방법을 결과에 담아 돌려준다(멈추지 않음)
        est = None
        errors.append(dict(code='MISSING_DATA_FILE', message=str(e).split('\n')[0], how_to=str(e)))
    month_known = cond['target_month'] is not None
    # ⑤ 결과
    ue = []
    if est:
        for key, item in est['items'].items():
            n = {v: k for k, v in A.UTIL_KEY.items()}[key]
            ai = ad['items'][n]
            row = dict(utility_type=TYPE_NAME[key], inclusion=ai['inclusion'], billing_basis=ai['billing_basis'], metering=ai['metering'],
                       advertised_amount_krw=ai['advertised_amount_krw'], user_confirmed=ai['user_confirmed'])
            if item.get('state') == 'HOLD':
                row.update(estimate_status='HOLD', reference_low_krw=None, reference_high_krw=None, reference_groups=[], hold_reason=item['reason'])
            elif not month_known:
                row.update(estimate_status='PENDING', reference_low_krw=None, reference_high_krw=None, reference_groups=[], hold_reason='기준 월이 없어 계산하지 않았습니다.')
            else:
                row.update(estimate_status='AVAILABLE', reference_low_krw=item['low'], reference_high_krw=item['high'],
                           reference_groups=[dict(group=v['view'], category=v['category'], bill_krw=v['bill'], usage=v['usage']) for v in item['by_view']],
                           hold_reason=None)
            ue.append(row)
    dec = (est or {}).get('decomposition') or dict(type='NONE', reason='광고에서 읽은 포함 항목이 없어 구성을 나누지 않습니다.')
    dec_status = {'NONE': 'NOT_APPLICABLE', 'HOLD': 'HOLD'}.get(dec['type'], 'AVAILABLE')
    dreasons = []
    if 'UNIT_OUT_OF_RANGE' in reasons:
        dreasons.append('UNIT_OUT_OF_RANGE')
    if 'INCLUSION_CONFLICT' in reasons:
        dreasons.append('INCLUSION_CONFLICT')
    if 'PARSE_INCOMPLETE_UNCONFIRMED' in reasons:
        dreasons.append('PARSE_INCOMPLETE_UNCONFIRMED')
    if total is None:
        dreasons.append('MISSING_TOTAL')
    if not included:
        dreasons.append('NO_INCLUDED_ITEMS')
    if not month_known:
        dreasons.append('CONDITION_MISSING:target_month')
    rest_inc = [n for n in included if ad['items'][n]['advertised_amount_krw'] is None]
    if rest_inc and any(ad['items'][n]['metering'] != 'INDIVIDUAL' for n in rest_inc):
        dreasons.append('METERING_UNKNOWN' if any(ad['items'][n]['metering'] == 'UNKNOWN' for n in rest_inc) else 'METERING_SHARED')
    if est and any(est['items'].get(A.UTIL_KEY[n], {}).get('state') == 'HOLD' for n in rest_inc):
        dreasons.append('REFERENCE_HOLD')
    # 입력 충돌 · 단위 의심 · 읽기 불완전(미확인) · 기준 월 없음 · 참고 비용 보류 항목이 있으면 구성 보기는 항상 HOLD (계산 결과가 있어도 보여 주지 않음)
    if set(dreasons) & {'UNIT_OUT_OF_RANGE', 'INCLUSION_CONFLICT', 'PARSE_INCOMPLETE_UNCONFIRMED', 'CONDITION_MISSING:target_month', 'REFERENCE_HOLD'}:
        dec_status = 'HOLD'
    decomposition = dict(enabled=bool(p.get('experimental_remainder')), status=dec_status, kind=dec['type'] if dec_status == 'AVAILABLE' else None, basis='SIMULATED' if dec['type'] in ('VIRTUAL', 'MIXED') else ('ADVERTISED' if dec['type'] == 'ACTUAL' else None),
                         label=dec.get('label') if dec_status == 'AVAILABLE' else None,
                         remainder_low_krw=dec.get('R_low') if dec_status == 'AVAILABLE' else None,
                         remainder_high_krw=dec.get('R_high') if dec_status == 'AVAILABLE' else None,
                         advertised_items_sum_krw=dec.get('actual_sum') if dec_status == 'AVAILABLE' else None,
                         reference_items_low_krw=dec.get('U_low') if dec_status == 'AVAILABLE' else None,
                         reference_items_high_krw=dec.get('U_high') if dec_status == 'AVAILABLE' else None,
                         reason_codes=sorted(set(dreasons)) if dec_status != 'AVAILABLE' else [],
                         reason=(dec.get('reason') if dec_status != 'AVAILABLE' else None))
    if dec['type'] == 'HOLD' and not decomposition['reason_codes'] and dec_status == 'HOLD':
        r = dec.get('reason', '')
        decomposition['reason_codes'] = ['ITEM_SUM_EXCEEDS_TOTAL'] if '합이 관리비 총액보다' in r else (['REFERENCE_EXCEEDS_TOTAL'] if '참고 비용이 광고 관리비 이상' in r else ['GAS_UNCONFIRMED'] if '가스' in r else ['HOLD'])
    # 상태
    status = (est or {}).get('status', 'INSUFFICIENT_DATA')
    status_reason = []
    if est is None:
        status = 'INSUFFICIENT_DATA'; status_reason.append('MISSING_DATA_FILE' if errors else 'NO_USABLE_AD_INFO')
    elif status == 'REVIEW_REQUIRED':
        status = 'REFERENCE_ONLY'      # 광고 금액이 참고 구간보다 크다는 이유로 '확인 필요' 상태를 만들지 않는다(차이는 reference_comparison 에 사실로만 적는다)
    if not errors and (ad['conflicts'] or ad.get('parse_incomplete_unresolved') or 'ITEM_SUM_EXCEEDS_TOTAL' in reasons):      # 입력 확인이 필요하면(참고 계산이 없어도) REVIEW_REQUIRED. 서버 환경 오류(errors)는 별개
        status = 'REVIEW_REQUIRED'; status_reason.append('INPUT_NEEDS_CONFIRMATION')
    if status == 'INSUFFICIENT_DATA' and not status_reason:
        status_reason.append('NO_REFERENCE_AVAILABLE')
    if est:
        questions = list(dict.fromkeys(questions + est['questions']))
    all_reasons = sorted(set(reasons + decomposition['reason_codes']))
    if not decomposition['enabled']:      # 기본: 총액에서 역산한 '나머지 금액'을 결과에 싣지 않는다(기타를 임의로 만들지 않음)
        all_reasons = sorted(set(reasons))      # 구성 보기 전용 사유(METERING_UNKNOWN, REFERENCE_* 등)는 꺼진 계산이므로 싣지 않는다
        decomposition = dict(enabled=False, status='DISABLED', remainder_low_krw=None, remainder_high_krw=None,
                             note='총액에서 알려진 항목을 빼서 기타 금액을 만들지 않습니다. 실험용 계산은 experimental_remainder=true 일 때만 내부 확인용으로 제공합니다.')
    comparison = []                       # 광고 금액과 참고 구간의 차이: 상태와 무관한 사실 기록(정상·비정상 판단 아님)
    for key, info in ((est or {}).get('assess_items') or {}).items():
        amt, hi, lo = info.get('amount'), info.get('reference_high'), info.get('reference_low')
        if amt is not None and hi:
            comparison.append(dict(utility_type=TYPE_NAME.get(key, key.upper()), advertised_amount_krw=amt, reference_low_krw=lo, reference_high_krw=hi,
                                   ratio_to_reference_high=round(amt / hi, 2), comparable=ad['items'][{v: k for k, v in A.UTIL_KEY.items()}[key]]['metering'] in ('INDIVIDUAL',),
                                   limitations='참고 구간은 2023년 조사 가구의 중간 50%를 요금으로 바꾼 값이며 정상 범위가 아닙니다. 개별·공동 계량, 정액·실비, 사용 패턴에 따라 청구 금액은 달라질 수 있습니다.'))
    sep = [dict(utility_type=TYPE_NAME[k], note='광고에서 별도로 내는 항목이라 관리비 안의 합계에 넣지 않았습니다.',
                reference_low_krw=v.get('low'), reference_high_krw=v.get('high'), hold=v.get('hold')) for k, v in ((est or {}).get('separate') or {}).items()]
    recent = None
    try:
        from . import recent_ref
        if recent_ref.available() and month_known:
            recent = recent_ref.recent_snapshot(cond['target_month'])
    except Exception:
        recent = None
    other_block = ad.get('other') or dict(inclusion='UNKNOWN', advertised_amount_krw=None, amount_source='NOT_PROVIDED',
                                          descriptions=[x for x in ad.get('other_included', [])], legacy_components=[],
                                          note='기타는 광고에 명시된 금액만 표시하며 총액에서 다른 항목을 빼서 만들지 않습니다.')
    if other_block['advertised_amount_krw'] is None and ad.get('other_amounts_krw'):      # 광고 상세보기에서 읽은 공용·기타 금액(명시된 값)
        oa = ad['other_amounts_krw']
        other_block = dict(other_block, advertised_amount_krw=sum(oa.values()), amount_source='ADVERTISED', advertised_parts_krw=oa)
    return dict(
        schema_version=SCHEMA_VERSION, request_id=p.get('request_id'), calculation_version=CALCULATION_VERSION,
        source_contract_version=source_cv, tariff_version=(est or {}).get('meta', {}).get('tariff_date'),
        status=status, status_reason=status_reason,
        advertised=dict(maintenance_total_krw=total, total_source=ad.get('total_source', 'AD'), mode=ad['mode'], undisclosed=ad['undisclosed'],
                        parse_incomplete=ad['parse_incomplete'], incomplete_reasons=ad['incomplete_reasons'],
                        parse_incomplete_unresolved=bool(ad.get('parse_incomplete_unresolved')), user_confirmed=bool(ad.get('user_confirmed')),
                        conflicts=ad['conflicts'], other_included=ad['other_included']),
        items=dict(OTHER=other_block, internet_availability=ad.get('internet_availability')),
        conditions_used=dict(cond),
        utility_estimates=ue, separate_items=sep, reference_comparison=comparison, decomposition=decomposition,
        missing_fields=miss, reason_codes=all_reasons, warnings=warnings, input_warnings=input_warnings, confirmation_questions=questions,
        assumptions=dict(usage_source='KESIS 가구에너지패널조사 14차(2023) 서울 결과표', tariff_version=(est or {}).get('meta', {}).get('tariff_date'),
                         unverified_parameters=_unverified(), note='2023년 사용량을 2026년 요율로 환산한 참고 금액이며 실제 청구액이 아닙니다. 표시한 폭은 서로 다른 집단 평균을 각각 환산한 값들의 최소~최대이며 정상 범위가 아닙니다.'),
        recent_reference=recent, errors=errors, never=NEVER)
