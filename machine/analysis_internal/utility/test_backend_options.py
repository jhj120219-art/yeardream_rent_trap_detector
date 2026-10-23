# -*- coding: utf-8 -*-
"""백엔드 FIVE_ITEMS_V1 입력 변환(backend_options.py)과 run_maintenance 기본 동작 시험.
- 만원 -> 원(Decimal, 1원 미만은 오류), null / 0 구분, SEPARATE_CHARGE 매핑, 인터넷 AVAILABLE, OTHER 금액 비생성, 예전 청소·공용 보존
- 기본 동작: 나머지 금액(구성 보기) 꺼짐, REVIEW_REQUIRED 는 입력 확인 전용(참고 구간 초과로 올리지 않음), 계약 버전·입력 검증 오류
실행: python -X utf8 -m utility.test_backend_options   (analysis_internal 에서. energy_reference_2023.csv 필요)"""
import json

from . import backend_options as BO
from .data_files import MissingDataFile, require_energy_reference
from .integration import run_maintenance, STATUSES

try:
    require_energy_reference()
except MissingDataFile as _e:
    print('이 시험에는 energy_reference_2023.csv 가 필요합니다.\n' + str(_e))
    raise SystemExit(2)

FAILS = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + (f'  {detail}' if (detail and not cond) else ''))
    if not cond:
        FAILS.append(name)


COND = dict(target_month=10, household_size=1, housing_type='다세대·연립', area_m2=20)
FORBID = ['부당', '눈탱이', '바가지', '과다 청구', '폭리', '사기', '정상 관리비', '적정', 'OVERPRICED']


def opts(**kw):
    base = dict(maintenance_10k_krw=8, electricity_in_maintenance='SEPARATE_CHARGE', electricity_10k_krw=None, water_in_maintenance='INCLUDED', water_10k_krw=1,
                gas_in_maintenance='UNKNOWN', gas_10k_krw=None, internet_status='INCLUDED', internet_10k_krw=None, other_in_maintenance='INCLUDED',
                other_10k_krw=None, other_cost_label='청소·공용관리 포함, 상세 금액 미기재', maintenance_note=None)
    base.update(kw)
    return base


def conv(**kw):
    ad, err = BO.normalize_backend_options(opts(**kw))
    return ad, err


# --- 단위 · null · 0 ---
ad, err = conv()
check('만원 -> 원: 관리비 8만원 = 80,000', ad['maintenance_total_krw'] == 80000 and not err)
check('항목 1만원 = 10,000원, 포함 + 금액이면 FIXED', ad['items']['수도']['advertised_amount_krw'] == 10000 and ad['items']['수도']['billing_basis'] == 'FIXED')
ad, _ = conv(water_10k_krw=0.5)
check('0.5만원 = 5,000원 (float 오차 없음)', ad['items']['수도']['advertised_amount_krw'] == 5000)
ad, _ = conv(maintenance_10k_krw=44.9)
check('44.9만원 = 449,000원', ad['maintenance_total_krw'] == 449000)
ad, _ = conv(maintenance_10k_krw=None)
check('관리비 null 은 null (0원으로 바꾸지 않음)', ad['maintenance_total_krw'] is None)
ad, _ = conv(maintenance_10k_krw=0)
check('관리비 0 은 명시된 0원', ad['maintenance_total_krw'] == 0)
ad, _ = conv(water_10k_krw=None)
check('항목 금액 null 은 null', ad['items']['수도']['advertised_amount_krw'] is None)
ad, err = conv(maintenance_10k_krw=8.12345)
check('1원 미만이 생기는 값(8.12345만원)은 반올림하지 않고 오류', any(e['code'] == 'INVALID_AMOUNT' and 'FRACTIONAL_WON' in e['message'] for e in err), str(err))
ad, err = conv(water_10k_krw='8만원')
check('금액 필드에 "8만원" 문자열은 오류', any(e['field'] == 'water_10k_krw' for e in err))
ad, err = conv(water_10k_krw='8.5')
check('숫자 모양 문자열 "8.5" 는 숫자로 읽음', ad['items']['수도']['advertised_amount_krw'] == 85000 and not err)
for bad in (-1, float('inf'), float('nan'), True):
    _, err = conv(gas_10k_krw=bad)
    check(f'금액 {bad!r} 는 검증 오류', bool(err), str(err))
_, err = conv(electricity_in_maintenance='MAYBE')
check('알 수 없는 포함 상태는 INVALID_STATUS', any(e['code'] == 'INVALID_STATUS' for e in err))
_, err = BO.normalize_backend_options('not a dict')
check('options 가 객체가 아니면 INVALID_INPUT', any(e['code'] == 'INVALID_INPUT' for e in err))

# --- 포함 여부 매핑 ---
ad, _ = conv()
check('SEPARATE_CHARGE -> SEPARATE', ad['items']['전기']['inclusion'] == 'SEPARATE')
check('INCLUDED -> INCLUDED, UNKNOWN -> UNKNOWN (임의 결정 금지)', ad['items']['수도']['inclusion'] == 'INCLUDED' and ad['items']['가스']['inclusion'] == 'UNKNOWN')
ad, _ = conv(electricity_in_maintenance='SEPARATE_CHARGE', electricity_10k_krw=2)
check('전기 별도 + 금액 2만원: 관리비 안의 금액으로 쓰지 않음(separate_amount_krw 에만)', ad['items']['전기']['advertised_amount_krw'] is None and ad['items']['전기'].get('separate_amount_krw') == 20000)
ad, _ = conv(gas_in_maintenance='UNKNOWN', gas_10k_krw=3)
check('포함 여부 UNKNOWN 인 항목의 금액은 계산에 쓰지 않고 경고', ad['items']['가스']['advertised_amount_krw'] is None and any(w['code'] == 'AMOUNT_WITHOUT_INCLUSION' for w in ad['input_warnings']))
ad, err = conv(internet_status='AVAILABLE')
check('인터넷 AVAILABLE: 이용 가능만 기록, 포함 여부는 UNKNOWN', ad['items']['인터넷']['inclusion'] == 'UNKNOWN' and ad['internet_availability'] == 'AVAILABLE' and not err)
ad, _ = conv(internet_status='NOT_AVAILABLE')
check('인터넷 NOT_AVAILABLE 도 포함 여부 UNKNOWN', ad['items']['인터넷']['inclusion'] == 'UNKNOWN' and ad['internet_availability'] == 'NOT_AVAILABLE')

# --- OTHER ---
ad, _ = conv()
check('OTHER 는 설명만 있고 금액 null (NOT_PROVIDED)', ad['other']['advertised_amount_krw'] is None and ad['other']['amount_source'] == 'NOT_PROVIDED' and '청소·공용관리 포함, 상세 금액 미기재' in ad['other']['descriptions'])
ad, _ = conv(other_10k_krw=1.5)
check('OTHER 에 명시된 금액만 그대로(15,000원)', ad['other']['advertised_amount_krw'] == 15000 and ad['other']['amount_source'] == 'ADVERTISED')
ad, _ = conv(cleaning_in_maintenance='INCLUDED', cleaning_10k_krw=2, common_in_maintenance='INCLUDED', common_10k_krw=3, other_10k_krw=None)
check('예전 청소·공용 금액은 합치거나 OTHER 금액으로 만들지 않고 설명·legacy 로만 보존', ad['other']['advertised_amount_krw'] is None and len(ad['other']['legacy_components']) == 2
      and {'청소', '공용'} <= set(ad['other']['descriptions']) and any(w['code'] == 'LEGACY_OTHER_COMPONENTS' for w in ad['input_warnings']))

# --- run_maintenance: 기본 동작 ---
P = dict(backend_options=opts(), conditions=COND, user=dict(confirmed=True, metering='INDIVIDUAL'))
r = run_maintenance(dict(P, request_id='b1'))
check('FIVE_ITEMS_V1 입력 -> source_contract_version, calculation_version 기록', r['source_contract_version'] == 'FIVE_ITEMS_V1' and r['calculation_version'].startswith('utility-v'))
check('기본: 구성 보기(나머지 금액) 꺼짐, 나머지 금액 없음', r['decomposition']['enabled'] is False and r['decomposition']['status'] == 'DISABLED' and r['decomposition']['remainder_low_krw'] is None)
check('items.OTHER: 금액을 총액에서 만들지 않음(null)', r['items']['OTHER']['advertised_amount_krw'] is None and r['items']['OTHER']['amount_source'] == 'NOT_PROVIDED')
check('전기(별도)는 관리비 안 추정에서 빠지고 separate_items 에 따로', [u['utility_type'] for u in r['utility_estimates']] == ['WATER', 'INTERNET'] and [s['utility_type'] for s in r['separate_items']] == ['ELECTRICITY'], str(r['separate_items']))
check('참고 비용은 정상 계산(수도 AVAILABLE)', r['utility_estimates'][0]['estimate_status'] == 'AVAILABLE' and r['status'] == 'REFERENCE_ONLY', str(r['status']))
rx = run_maintenance(dict(P, experimental_remainder=True))
check('experimental_remainder=true 일 때만 내부 계산을 낸다', rx['decomposition']['enabled'] is True)

# --- 상태 의미: 참고 구간 초과로 REVIEW_REQUIRED 를 만들지 않는다 ---
high = run_maintenance(dict(P, backend_options=opts(water_10k_krw=20, maintenance_10k_krw=30)))
check('수도 광고 금액이 참고 구간의 1.5배 초과여도 상태는 REFERENCE_ONLY', high['status'] == 'REFERENCE_ONLY', high['status'])
cmp_w = [c for c in high['reference_comparison'] if c['utility_type'] == 'WATER']
check('  -> 차이는 reference_comparison 에 사실(금액·구간·비율·한계)로만', bool(cmp_w) and cmp_w[0]['ratio_to_reference_high'] > 1.5 and 'limitations' in cmp_w[0])
check('  -> 사유 코드에 AMOUNT_ABOVE_REFERENCE_RANGE 가 없다', 'AMOUNT_ABOVE_REFERENCE_RANGE' not in high['status_reason'] and 'AMOUNT_ABOVE_REFERENCE_RANGE' not in high['reason_codes'])
conf = run_maintenance(dict(ad=dict(total=60000, utility_included=['수도'], utility_separate=['수도']), conditions=COND))
check('입력 충돌(포함+별도)은 REVIEW_REQUIRED (입력 확인)', conf['status'] == 'REVIEW_REQUIRED' and 'INPUT_NEEDS_CONFIRMATION' in conf['status_reason'])

# --- 계약 버전 · 검증 오류 ---
bad = run_maintenance(dict(P, contract_version='FIVE_ITEMS_V9'))
check('지원하지 않는 계약 버전: UNSUPPORTED_CONTRACT_VERSION, 계산 안 함', bad['errors'][0]['code'] == 'UNSUPPORTED_CONTRACT_VERSION' and bad['utility_estimates'] == [])
inv = run_maintenance(dict(backend_options=opts(water_10k_krw=-3), conditions=COND))
check('입력 검증 오류: errors 에 INVALID_AMOUNT, INSUFFICIENT_DATA 이지만 사유는 입력 오류', inv['errors'][0]['code'] == 'INVALID_AMOUNT' and inv['status'] == 'INSUFFICIENT_DATA' and 'INVALID_AMOUNT' in inv['status_reason'])
non = run_maintenance('not a payload')
check('payload 가 객체가 아니면 INVALID_INPUT', non['errors'][0]['code'] == 'INVALID_INPUT')

# --- 전체 불변식 ---
samples = [r, rx, high, conf, bad, inv, non]
check('status 는 허용된 3가지뿐', all(x['status'] in STATUSES for x in samples))
blob = json.dumps(samples, ensure_ascii=False)
check('판정 용어 없음', not [w for w in FORBID if w in blob.replace('부당액으로 해석하지 않음', '').replace('부당 청구액으로 해석하지 않음', '')])
check('JSON 직렬화 가능', bool(blob))
check('모든 결과에 errors 키(없으면 빈 목록)', all(isinstance(x['errors'], list) for x in samples))

print('\n실패', len(FAILS), '건', FAILS if FAILS else '')
raise SystemExit(1 if FAILS else 0)
