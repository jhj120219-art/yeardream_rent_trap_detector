# -*- coding: utf-8 -*-
"""공과금 단가 상수. 값마다 확인 상태(verified)와 출처를 함께 둔다. 확인 상태가 False 인 값은 계산 결과에 '가정'으로 표시한다.
출처 확인일 2026-10-20. 원본 스냅샷은 data/utility_stats/web/, 정리본은 data/utility_stats/tariffs_20261020.json."""

ELECTRIC = dict(
    summer_months=(7, 8),
    tiers_summer=[(300, 910, 120.0), (450, 1600, 214.6), (None, 7300, 307.3)],     # (구간 상한 kWh, 기본요금 원/호, 전력량요금 원/kWh)
    tiers_other=[(200, 910, 120.0), (400, 1600, 214.6), (None, 7300, 307.3)],
    fuel_adjust_won_per_kwh=5.0,     # 2026년 4분기 연료비조정단가, 한전 공지 2026-09-21 (verified)
    climate_won_per_kwh=9.0,         # 기후환경요금: 비공식 계산기 기준 값, 공식 확인 필요 (unverified)
    fund_rate=0.027,                 # 전력산업기반기금율 2.7%: 2025.7.1부터(한전 요금표 공개 사본·정부 인하 발표). 이전 3.7%는 사용 안 함. 한전 원문 확인 전까지 잠정
    vat_rate=0.10,
    verified=dict(tiers=True, fuel_adjust=True, climate=False, fund=False, vat=True),
    source='https://cyber.kepco.co.kr/ckepco/front/jsp/CY/E/E/CYEEHP00101.jsp (주택용 저압, 적용일자 2023-05-16 표기)')

GAS = dict(
    won_per_mj=22.5268,              # 서울도시가스 주택용 취사·난방, 2026.10.01 (verified)
    base_won_per_month=1250,         # 서울도시가스 요금표 안내(검색 결과로 확인, 화면 재확인 권장)
    mj_per_nm3=43.0,                 # 월별 평균열량: 고지서 값으로 대체해야 함, 근사값 (unverified)
    correction=1.0,                  # 보정계수 (unverified)
    vat_rate=0.10,
    verified=dict(unit_price=True, base=True, heat=False),
    source='https://www.seoulgas.co.kr/mobile/payment/gasPayTable')

WATER = dict(
    base_won_per_month_15mm=1080,    # 아리수 요금계산 시뮬레이션 결과로 확인 (verified)
    waterworks_won_per_m3=580, sewerage_won_per_m3=480, water_use_charge_won_per_m3=170,
    verified=dict(all=True),
    source='https://i121.seoul.go.kr/cs/cyber/front/cgcalc/NR_cgCalcGeneralPurpose.do (가정용 1세대 15mm 10㎥ = 13,380원)')

# 서울시 세대원 수별 1일 평균 수돗물 사용량(L, 세대 합계, 2021년, 서울아리수본부 2023-09-14 보도자료)
SEOUL_WATER_L_PER_DAY = {1: 264, 2: 435, 3: 576, 4: 679, 5: 777, 6: 813}
