# -*- coding: utf-8 -*-
"""사용자 화면 4가지 상황이 안전하게 처리되는지 확인(ChatGPT 권고 P0). 실행: python -m utility.test_scenarios (analysis_internal 에서)"""
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('demo_app', Path(__file__).parent / 'demo' / 'app.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
base = dict(month=1, household=1, housing='다세대·연립', area_band='~33㎡', heating='모름', gas_user='모름')
ok = True


def c(name, cond):
    global ok
    ok &= bool(cond)
    print(('PASS ' if cond else 'FAIL ') + name)


r1 = m.estimate({**base, 'mgmt_man': '15'})
c('1) 관리비 총액만 -> INSUFFICIENT_DATA, 질문으로 포함 항목 확인', r1['status'] == 'INSUFFICIENT_DATA' and '포함되는 항목' in r1['questions'][0])
r2 = m.estimate({**base, 'mgmt_man': '15', 'included': ['수도', '인터넷']})
c('2) 총액+포함 항목 -> REFERENCE_ONLY, 합계를 총액에서 뺀 부당액 필드 없음', r2['status'] == 'REFERENCE_ONLY' and not any('unexplained' in k or 'overcharge' in k for k in r2))
r3 = m.estimate({**base, 'mgmt_man': '15', 'included': ['수도'], 'itemized': {'수도': 60000}})
c('3) 항목별 금액이 참고 금액과 크게 다르면 REVIEW_REQUIRED(확인 필요 이상 판정 없음)', r3['status'] == 'REVIEW_REQUIRED')
r4 = m.estimate({**base, 'included': ['가스']})
c('4) 난방·가스 사용 미확인이면 가스는 HOLD, 합계에 가스 미포함', r4['items']['gas']['state'] == 'HOLD' and r4['sum_high'] == 0)
r5 = m.estimate({**base, 'heating': '개별 도시가스', 'gas_user': '예', 'included': ['가스']})
c('5) 개별 도시가스 확인 시 가스 참고 금액 제공(여러 집단 평균 각각 표시)', r5['items']['gas'].get('by_view') and len(r5['items']['gas']['by_view']) >= 3)
r6 = m.estimate({**base, 'heating': '중앙·지역난방', 'included': ['가스']})
c('6) 지역난방은 도시가스 개별난방 추정 적용 금지', r6['items']['gas']['state'] == 'HOLD')
r7 = m.estimate({**base, 'included': ['수도'], 'excluded': ['전기']})
c('7) 별도 항목은 포함 항목과 분리해 따로 표시', 'electric' in r7['separate'] and 'electric' not in r7['items'])
c('8) 결과에 버전·기준 정보 포함', 'tariff_date' in r2['meta'] and '2023' in r2['meta']['usage_basis'])
print('SCENARIOS PASS' if ok else 'SCENARIOS FAIL')

# ---- 관리비 구성(분해) P0 테스트 (ChatGPT 권고)
print('--- 구성 보기')
ok = True
d_a = m.estimate({**base, 'mgmt_man': '15'})['decomposition']
c('D1) 총액만 -> 분해하지 않음', d_a['type'] == 'NONE')
d_b = m.estimate({**base, 'mgmt_man': '15', 'included': ['수도', '인터넷'], 'metering': '세대별'})['decomposition']
c('D2) 포함 항목+세대별 계량 -> VIRTUAL, 나머지=총액-참고비용 범위', d_b['type'] == 'VIRTUAL' and d_b['R_low'] == 150000 - d_b['U_high'] and d_b['R_high'] == 150000 - d_b['U_low'])
d_b2 = m.estimate({**base, 'mgmt_man': '15', 'included': ['수도', '인터넷']})['decomposition']
c('D3) 계량 방식 모름 -> 구성비 보류(참고 비용은 별도로 제공)', d_b2['type'] == 'HOLD' and d_b2.get('can_assume') is True)
d_c = m.estimate({**base, 'mgmt_man': '15', 'included': ['수도', '인터넷'], 'itemized': {'수도': 20000, '인터넷': 30000}})['decomposition']
c('D4) 항목별 금액이 모두 있으면 추정값을 더하지 않고 광고 금액만으로 나눔(ACTUAL)', d_c['type'] == 'ACTUAL' and d_c['R_low'] == 100000 and d_c['U_high'] == 0)
d_m = m.estimate({**base, 'mgmt_man': '15', 'included': ['수도', '인터넷'], 'itemized': {'수도': 20000}, 'metering': '세대별'})['decomposition']
c('D5) 일부만 금액이 있으면 해당 항목은 광고 금액, 나머지 항목만 참고 비용(MIXED)', d_m['type'] == 'MIXED' and d_m['ref_items'] == ['internet'] and d_m['actual_sum'] == 20000)
d_o = m.estimate({**base, 'mgmt_man': '3', 'included': ['수도', '인터넷'], 'metering': '세대별'})['decomposition']
c('D6) 참고 비용이 총액 이상이면 음수·0 대신 산출 어려움(HOLD)', d_o['type'] == 'HOLD' and 'R_low' not in d_o)
d_g = m.estimate({**base, 'mgmt_man': '15', 'included': ['가스', '수도'], 'metering': '세대별'})['decomposition']
c('D7) 가스 사용·난방 미확인이면 포함 항목에 가스가 있어도 구성비 보류(미확인을 0원으로 보지 않음)', d_g['type'] == 'HOLD')
d_p = m.estimate({**base, 'mgmt_man': '15', 'included': ['수도'], 'excluded': ['전기'], 'metering': '세대별'})
c('D8) 포함되지 않은(별도) 항목은 분해에서 빼지 않고 별도 목록으로만', 'electric' in d_p['separate'] and d_p['decomposition']['ref_items'] == ['water'])
b = m.estimate({**base, 'mgmt_man': '15', 'included': ['전기'], 'metering': '세대별', 'bill_usage': {'electric': 250}})
c('D9) 고지서 사용량이 있으면 공식 요금표 계산값 제공', b['bill_check'].get('electric', 0) > 0)
c('D10) 결과 문구에 부당·눈탱이·과다 청구 용어 없음', not any(w in str(d_b) for w in ('부당 청구 의심', '눈탱이', '과다 청구')))
print('DECOMP PASS' if ok else 'DECOMP FAIL')
