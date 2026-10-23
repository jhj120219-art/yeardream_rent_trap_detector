# -*- coding: utf-8 -*-
"""adapter.py / integration.run_maintenance 경계 사례 시험 (ChatGPT 권고 16종 + 통합 불변식).
실행: python -X utf8 -m utility.test_adapter   (analysis_internal 에서)"""
import json
import re

from . import adapter as A
from .data_files import MissingDataFile, require_energy_reference
from .integration import run_maintenance as _rm, STATUSES


def run_maintenance(payload):
    """이 파일의 구성 보기(나머지 금액) 시험은 실험용 계산을 켜고 실행한다. 기본(꺼짐) 동작은 맨 아래 별도 시험과 test_backend_options 에서 확인한다."""
    return _rm(dict(payload, experimental_remainder=True)) if isinstance(payload, dict) else _rm(payload)


try:
    require_energy_reference()
except MissingDataFile as _e:          # 데이터 파일이 없으면 이유를 알리고 멈춘다(실패와 구분되는 종료 코드 2)
    print('이 시험에는 energy_reference_2023.csv 가 필요합니다.\n' + str(_e))
    raise SystemExit(2)

FAILS = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + (f'  {detail}' if (detail and not cond) else ''))
    if not cond:
        FAILS.append(name)


def ext(**kw):
    base = dict(total=None, mode='불명', undisclosed=False, included=[], excluded_items=[], amounts={}, actual_items=[], not_provided=[],
                utility_included=[], utility_separate=[], incomplete=[], notes=[])
    base.update(kw)
    return base


COND = dict(target_month=10, household_size=1, housing_type='다세대·연립', area_m2=20, heating_type='모름', gas_user='모름')
FORBID = ['부당', '눈탱이', '바가지', '과다 청구', '폭리', '사기', '정상 관리비', '적정', 'OVERPRICED']

# --- 금액 단위 ---
check('금액: 8만원', A.parse_krw('8만원') == 80000)
check('금액: 8.5만원', A.parse_krw('8.5만원') == 85000)
check('금액: 8만 5천원', A.parse_krw('8만 5천원') == 85000)
check('금액: 80,000원', A.parse_krw('80,000원') == 80000)
check('금액: 명시된 0원은 0', A.parse_krw('0원') == 0 and A.parse_krw(0) == 0)
check('금액: 없음/해석불가는 None(0으로 바꾸지 않음)', A.parse_krw('없음') is None and A.parse_krw(None) is None and A.parse_krw('') is None and A.parse_krw('-5만원') is None)
check('금액: 만원 입력 8.5 -> 85000(float 오차 없음)', A.man_to_krw(8.5) == 85000 and A.man_to_krw('0.1') == 1000 and A.man_to_krw(44.9) == 449000)
n0 = A.normalize_ad(ext())
check('누락: 총액 없음은 None', n0['maintenance_total_krw'] is None)
n0z = A.normalize_ad(ext(total=0))
check('총액 0원은 0(명시값)', n0z['maintenance_total_krw'] == 0)

# --- 포함/별도/불명/충돌 ---
n1 = A.normalize_ad(ext(total=80000, utility_included=['수도'], utility_separate=['전기'], actual_items=['전기']))
check('수도 포함 + 전기 별도: 수도만 분해 대상', [k for k, v in n1['items'].items() if v['inclusion'] == 'INCLUDED'] == ['수도'] and n1['items']['전기']['inclusion'] == 'SEPARATE')
p1 = A.to_demo_params(n1, COND)
check('  -> estimate 입력: included=[수도], excluded=[전기]', p1['included'] == ['수도'] and p1['excluded'] == ['전기'])
n2 = A.normalize_ad(ext(total=60000, utility_separate=['수도'], actual_items=['수도']))
check('수도 별도 실비: SEPARATE, 포함 목록에서 제외', n2['items']['수도']['inclusion'] == 'SEPARATE' and A.to_demo_params(n2, COND)['included'] == [])
n3 = A.normalize_ad(ext(total=60000, utility_included=['수도'], utility_separate=['수도']))
check('수도 포함+별도 충돌: conflicts 로 표시, 어느 쪽도 고르지 않음', n3['conflicts'] == ['수도'] and n3['items']['수도']['inclusion'] == 'UNKNOWN')
r3 = run_maintenance(dict(ad=ext(total=60000, utility_included=['수도'], utility_separate=['수도']), conditions=COND))
check('  -> 결과: 분해 HOLD + INCLUSION_CONFLICT', r3['decomposition']['status'] == 'HOLD' and 'INCLUSION_CONFLICT' in r3['reason_codes'], str(r3['decomposition']))
n4 = A.normalize_ad(ext(total=80000, utility_included=['수도'], included=['수도']))
check('전기 미표시: UNKNOWN (SEPARATE 로 추정 안 함)', n4['items']['전기']['inclusion'] == 'UNKNOWN')

# --- 항목 금액 · 중복 · 합계 ---
r5 = run_maintenance(dict(ad=ext(total=80000, utility_included=['수도'], amounts={'수도': 20000}, mode='정액'), conditions=COND,
                          user=dict(confirmed=True, metering='INDIVIDUAL')))
d5 = r5['decomposition']
check('수도 2만 원 명시: 표기액 사용, 추정액을 다시 차감하지 않음(ACTUAL, 나머지 6만)', d5['status'] == 'AVAILABLE' and d5['kind'] == 'ACTUAL' and d5['remainder_low_krw'] == 60000 == d5['remainder_high_krw'], str(d5))
n6 = A.normalize_ad(ext(total=80000, utility_included=['수도'], amounts={'수도': 20000, '공용': 60000}))
p6 = A.to_demo_params(n6, COND)
check('같은 항목 중복 합산 방지: itemized 수도는 1회', list(p6['itemized'].items()) == [('수도', 20000)])
txt = ('관리비 합계 449,000 원 정액관리비 공용 관리비 99,000 원 사용료 350,000 원 전기 50,000 원 수도 50,000 원 가스 50,000 원 난방 50,000 원 인터넷 50,000 원 TV 100,000 원 '
       '포함 항목 : 전기, 수도, 가스, 난방, 인터넷, TV 미포함 항목 : 없음')
r7 = run_maintenance(dict(ad_text=txt, conditions=COND))
check('합계 일치(44.9만 = 공용 9.9 + 사용료 35): 불완전 사유 없음', not r7['advertised']['parse_incomplete'], str(r7['advertised']['incomplete_reasons']))
r8 = run_maintenance(dict(ad=ext(total=50000, utility_included=['수도', '전기'], amounts={'수도': 30000, '전기': 40000}, mode='정액'), conditions=COND,
                          user=dict(confirmed=True, metering='INDIVIDUAL')))
check('항목 합계 > 총액: 분해 HOLD, 음수 나머지 없음', r8['decomposition']['status'] == 'HOLD' and r8['decomposition']['remainder_low_krw'] is None and 'ITEM_SUM_EXCEEDS_TOTAL' in r8['reason_codes'], str(r8['decomposition']))

# --- 불완전 + 사용자 확인 ---
inc_ad = ext(total=100000, utility_included=['수도', '인터넷'], incomplete=['사용료 하위 항목 누락: 전기'], mode='정액')
r9a = run_maintenance(dict(ad=inc_ad, conditions=COND))
check('불완전 + 사용자 미확인: REVIEW_REQUIRED(입력 확인) + 분해 HOLD', r9a['status'] == 'REVIEW_REQUIRED' and 'INPUT_NEEDS_CONFIRMATION' in r9a['status_reason'] and r9a['decomposition']['status'] == 'HOLD')
r9b = run_maintenance(dict(ad=inc_ad, conditions=COND, user=dict(confirmed=True, resolves_incomplete=True, metering='INDIVIDUAL')))
check('불완전 + 사용자가 확인: 정상 계산 허용(원본 불완전 기록은 남음)', r9b['advertised']['parse_incomplete'] and not r9b['advertised']['parse_incomplete_unresolved'] and r9b['decomposition']['status'] == 'AVAILABLE', str(r9b['decomposition']))

# --- 계량 방식 ---
n10 = A.normalize_ad(ext(total=60000, mode='실비', utility_included=['수도'], actual_items=['수도']))
check('실비만 표기: billing_basis=ACTUAL 이지만 metering 은 UNKNOWN 유지', n10['items']['수도']['billing_basis'] == 'ACTUAL' and n10['items']['수도']['metering'] == 'UNKNOWN')
r10 = run_maintenance(dict(ad=ext(total=60000, mode='실비', utility_included=['수도']), conditions=COND))
check('  -> 계량 미확인이면 분해 HOLD + METERING_UNKNOWN', r10['decomposition']['status'] == 'HOLD' and 'METERING_UNKNOWN' in r10['reason_codes'], str(r10['decomposition']))

# --- 단위/범위 ---
r11 = run_maintenance(dict(ad=ext(total=8_000_000, utility_included=['수도']), conditions=COND))
check('총액이 월 500만원 초과: 단위 혼동 의심(UNIT_OUT_OF_RANGE), 분해 HOLD', 'UNIT_OUT_OF_RANGE' in r11['reason_codes'] and r11['decomposition']['status'] == 'HOLD')

# --- 조건 누락: 임의 가정 금지 ---
r12 = run_maintenance(dict(ad=ext(total=80000, utility_included=['수도', '전기'], mode='정액'), conditions={}))
check('조건 전부 없음: 크래시 없이 보류 + missing_fields', {'household_size', 'housing_type', 'area', 'target_month'} <= set(r12['missing_fields']) and r12['status'] in STATUSES, str(r12['missing_fields']))
check('  -> 기준 월 없으면 금액을 내지 않음', all(u['reference_low_krw'] is None for u in r12['utility_estimates']))
r13 = run_maintenance(dict(ad=ext(total=80000, utility_included=['전기'], mode='정액'), conditions=dict(target_month=10)))
check('가구원 수·면적·유형을 모르면 전기 참고 비용도 임의로 만들지 않음(HOLD)', r13['utility_estimates'][0]['estimate_status'] == 'HOLD', str(r13['utility_estimates']))
r14 = run_maintenance(dict(ad=ext(), conditions=COND))
check('광고 정보 전혀 없음: INSUFFICIENT_DATA', r14['status'] == 'INSUFFICIENT_DATA')
r15 = run_maintenance(None)
check('payload 없음: 크래시 없이 INSUFFICIENT_DATA', r15['status'] == 'INSUFFICIENT_DATA')

# --- 별도 실비는 합계에 넣지 않음 ---
r16 = run_maintenance(dict(ad=ext(total=70000, utility_included=['수도'], utility_separate=['전기'], actual_items=['전기'], mode='혼합'), conditions=COND,
                           user=dict(confirmed=True, metering='INDIVIDUAL')))
kinds = {u['utility_type'] for u in r16['utility_estimates']}
check('별도 실비(전기)는 utility_estimates(관리비 안)에 없고 separate_items 에 따로 표시', kinds == {'WATER'} and [s['utility_type'] for s in r16['separate_items']] == ['ELECTRICITY'], str((kinds, r16['separate_items'])))

# --- 전체 불변식 ---
samples = [r3, r5, r7, r8, r9a, r9b, r10, r11, r12, r13, r14, r15, r16]
check('status 는 허용된 3가지뿐', all(r['status'] in STATUSES for r in samples))
blob = json.dumps(samples, ensure_ascii=False)
check('판정 용어 없음', not [w for w in FORBID if w in blob.replace('부당액으로 해석하지 않음', '').replace('부당 청구액으로 해석하지 않음', '')])
check('나머지 금액은 음수가 아님', all((r['decomposition']['remainder_low_krw'] or 0) >= 0 for r in samples))
check('결과에 schema_version·never 가 항상 있음', all(r['schema_version'] == 'maintenance.v1' and r['never'] for r in samples))
check('JSON 직렬화 가능', bool(blob))

print('\n실패', len(FAILS), '건', FAILS if FAILS else '')
raise SystemExit(1 if FAILS else 0)
