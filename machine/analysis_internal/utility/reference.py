# -*- coding: utf-8 -*-
"""가구에너지패널 14차(2023) 서울 결과표 -> 참고 사용량·요금. 표마다 조건이 달라 서로 곱하지 않고 '관점별'로 따로 보여준다.
월별 사용량 = 서울 가구 평균 월별 프로파일 x (선택 조건 연간 평균 / 서울 전체 연간 평균)  <- 이 월 배분은 가정이며 조사된 값이 아니다."""
import csv
from .calc import electricity_bill, gas_bill, water_bill
from .data_files import energy_reference_csv, require_energy_reference
from .tariffs import SEOUL_WATER_L_PER_DAY

CSV = energy_reference_csv()      # 호환용(참고 경로). 실제로 열 때는 require_energy_reference() 가 없으면 어떤 파일이 없는지 알려 준다
_cache = None


def _load():
    global _cache
    if _cache is None:
        path = require_energy_reference()
        _cache = [r for r in csv.DictReader(open(path, encoding='utf-8-sig')) if r['region'] == '서울' and r['table'].startswith('3_')]
    return _cache


def _get(sheet, category, item):
    for r in _load():
        if r['sheet'].endswith(sheet) and r['category'] == category and r['item'] == item and r['estimate'] != '':
            return float(r['estimate']), (float(r['rse_pct']) if r['rse_pct'] != '' else None)
    raise KeyError((sheet, category, item))


VIEWS = {'housing': ('주택종류별', ['단독', '다세대/연립/기타', '아파트']), 'size': ('가구원수별', ['1명', '2명', '3명', '4명이상']),
         'area': ('주택면적별', ['33㎡미만', '33-66㎡미만', '66-99㎡미만', '99-132㎡미만', '132㎡이상']),
         'heating': ('주난방연료별', ['도시가스', '지역난방', '전기'])}   # 서울 표본: 도시가스 917가구, 지역난방 146, 전력 15(소표본, 추정 불안정)


def monthly_profile(item):
    return {m: _get('월별', f'{m}월', item)[0] for m in range(1, 13)}


def estimate(view: str, category: str, month: int, household_size: int = 1) -> dict:
    """한 관점(주택종류/가구원수/면적)에 따른 서울 참고 월 공과금(전기+가스+수도)."""
    sheet = VIEWS[view][0]
    out = {}
    for item, fn, key in (('일반전기', electricity_bill, 'electricity'), ('도시가스', gas_bill, 'gas')):
        annual, rse = _get(sheet, category, item)
        total, _ = _get(sheet, '합계', item)
        prof = monthly_profile(item)
        scale = annual / total
        usage = prof[month] * scale
        out[key] = dict(usage=round(usage, 1), annual=annual, rse_pct=rse, bill=fn(usage, month)['total'] if key == 'electricity' else fn(usage)['total'])
    liters = SEOUL_WATER_L_PER_DAY.get(min(household_size, 6), 435)
    m3 = liters * 30.4 / 1000
    out['water'] = dict(usage=round(m3, 1), bill=water_bill(m3)['total'], note='서울시 세대원 수별 1일 평균 사용량(2021)')
    out['total'] = out['electricity']['bill'] + out['gas']['bill'] + out['water']['bill']
    return out
