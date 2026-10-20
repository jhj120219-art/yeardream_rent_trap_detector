# -*- coding: utf-8 -*-
"""공과금 계산기 기본 검증. 실행: python -m utility.test_utility  (analysis_internal 폴더에서)"""
from .calc import electricity_bill, gas_bill, water_bill
from . import reference as R

ok = True


def check(name, cond, detail=''):
    global ok
    ok &= bool(cond)
    print(('PASS ' if cond else 'FAIL ') + name, detail)


check('수도 10㎥ = 아리수 계산기 결과 13,380원', 1080 + 10 * (580 + 480 + 170) == 13380 and water_bill(10)['total'] == 13380)
check('전기: 사용량 0이면 기본요금 구간 1 적용', electricity_bill(0, 3)['base'] == 910)
check('전기: 구간 경계 200kWh(기타계절)는 1구간 단가', electricity_bill(200, 3)['energy'] == 200 * 120)
check('전기: 201kWh는 2구간 단가가 1kWh에만 적용', electricity_bill(201, 3)['energy'] == round(200 * 120 + 214.6))
check('전기: 하계(8월) 300kWh는 1구간(상한 300)', electricity_bill(300, 8)['base'] == 910)
check('전기: 사용량이 늘면 요금도 증가', electricity_bill(350, 3)['total'] > electricity_bill(300, 3)['total'])
check('가스: 사용량 0이면 기본요금에 부가세', gas_bill(0)['total'] == 1380)
check('전기·가스 가정 표시', 'climate' in electricity_bill(100, 1)['assumptions'] and 'heat' in gas_bill(10)['assumptions'])
e = R.estimate('size', '1명', 1, 1)
check('서울 1인 가구 연간 전기 2,335.2kWh(결과표 값)', abs(e['electricity']['annual'] - 2335.2) < 0.01)
check('겨울 가스 요금이 여름보다 큼', R.estimate('size', '1명', 1, 1)['gas']['bill'] > R.estimate('size', '1명', 8, 1)['gas']['bill'])
print('ALL PASS' if ok else 'SOME FAIL')

# ---- 관리비 점검 규칙
from .check import assess
ok2 = True


def c2(name, cond):
    global ok2
    ok2 &= bool(cond)
    print(('PASS ' if cond else 'FAIL ') + name)


c2('포함 항목이 없으면 INSUFFICIENT_DATA', assess(month=1, mgmt_total=150000)['status'] == 'INSUFFICIENT_DATA')
c2('포함 항목만 있으면 REFERENCE_ONLY(비교 안 함)', assess(month=1, included=['water', 'internet'], mgmt_total=150000)['status'] == 'REFERENCE_ONLY')
c2('가스는 사용·난방 미확인이면 보류', assess(month=1, included=['gas'])['items']['gas']['state'] == 'HOLD')
c2('수도 청구가 참고 범위 상한의 1.5배 초과면 REVIEW_REQUIRED', assess(month=1, itemized={'water': 80000})['status'] == 'REVIEW_REQUIRED')
c2('수도 청구가 범위 안이면 REFERENCE_ONLY이며 과다 라벨 없음', assess(month=1, itemized={'water': 12000})['status'] == 'REFERENCE_ONLY')
c2('결과 상태에 OVERPRICED 같은 확정 라벨이 없음', all(assess(month=1, itemized={'water': 80000})['status'] != s for s in ('OVERPRICED', 'NORMAL')))
print('RULES PASS' if ok2 else 'RULES FAIL')
