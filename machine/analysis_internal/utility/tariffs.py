# -*- coding: utf-8 -*-
"""공과금 단가 상수. 단일 원본은 tariff_data/tariffs_2026-10.json (값마다 출처·확인 상태 status 를 함께 둠)이고, 이 모듈은 그 파일을 읽어
기존 계산기(calc.py)가 쓰는 ELECTRIC / GAS / WATER 딕셔너리 형태로 돌려준다. 확인 상태가 VERIFIED 가 아닌 값은 verified=False 가 되어
계산 결과에 '가정'으로 표시된다. 값을 바꿀 때는 이 파일이 아니라 JSON 을 고치고 test_tariff_data.py 를 실행한다."""
import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / 'tariff_data' / 'tariffs_2026-10.json'
DATA = json.loads(DATA_PATH.read_text(encoding='utf-8'))
TARIFF_SET_ID = DATA['tariff_set_id']


def _ok(item):
    return item.get('status') == 'VERIFIED'


def _tiers(rows):
    return [(r['up_to_kwh'], r['base_won'], r['won_per_kwh']) for r in rows]


_E, _G, _W = DATA['electricity'], DATA['gas'], DATA['water']
_EC = _E['components']

ELECTRIC = dict(
    summer_months=tuple(_E['summer_months']),
    tiers_summer=_tiers(_E['tiers']['summer']),      # (구간 상한 kWh, 기본요금 원/호, 전력량요금 원/kWh)
    tiers_other=_tiers(_E['tiers']['other']),
    fuel_adjust_won_per_kwh=_EC['fuel_adjust_won_per_kwh']['value'],
    climate_won_per_kwh=_EC['climate_won_per_kwh']['value'],
    fund_rate=_EC['fund_rate']['value'],
    vat_rate=_EC['vat_rate']['value'],
    verified=dict(tiers=_ok(_E['tiers']), fuel_adjust=_ok(_EC['fuel_adjust_won_per_kwh']), climate=_ok(_EC['climate_won_per_kwh']),
                  fund=_ok(_EC['fund_rate']), vat=_ok(_EC['vat_rate'])),
    source=_E['tiers']['source'])

GAS = dict(
    won_per_mj=_G['won_per_mj']['value'],
    base_won_per_month=_G['base_won_per_month']['value'],
    mj_per_nm3=_G['mj_per_nm3']['value'],
    correction=_G['correction']['value'],
    vat_rate=_G['vat_rate']['value'],
    verified=dict(unit_price=_ok(_G['won_per_mj']), base=_ok(_G['base_won_per_month']), heat=_ok(_G['mj_per_nm3'])),
    source=_G['won_per_mj']['source'])

WATER = dict(
    base_won_per_month_15mm=_W['base_won_per_month']['value'],
    waterworks_won_per_m3=_W['waterworks_won_per_m3']['value'],
    sewerage_won_per_m3=_W['sewerage_won_per_m3']['value'],
    water_use_charge_won_per_m3=_W['water_use_charge_won_per_m3']['value'],
    verified=dict(all=all(_ok(_W[k]) for k in ('base_won_per_month', 'waterworks_won_per_m3', 'sewerage_won_per_m3', 'water_use_charge_won_per_m3'))),
    source=_W['base_won_per_month']['source'] + f" (가정용 1세대 15mm {_W['anchor']['input_m3']}㎥ = {_W['anchor']['expected_total_won']:,}원)")

# 서울시 세대원 수별 1일 평균 수돗물 사용량(L, 세대 합계)
SEOUL_WATER_L_PER_DAY = {int(k): v for k, v in _W['seoul_l_per_day_by_household_size'].items()}
INTERNET_RANGE = tuple(DATA['internet']['range_won_per_month'])


def status_table():
    """값별 확인 상태 목록(문서·화면 점검용): [(항목, 값, status, 출처)]."""
    rows = []
    for k, v in _EC.items():
        rows.append(('전기 ' + k, v['value'], v['status'], v.get('source', '')))
    rows.append(('전기 누진 구간표', '3구간', _E['tiers']['status'], _E['tiers']['source']))
    for k in ('won_per_mj', 'base_won_per_month', 'mj_per_nm3', 'correction', 'vat_rate'):
        rows.append(('가스 ' + k, _G[k]['value'], _G[k]['status'], _G[k].get('source', '')))
    for k in ('base_won_per_month', 'waterworks_won_per_m3', 'sewerage_won_per_m3', 'water_use_charge_won_per_m3'):
        rows.append(('수도 ' + k, _W[k]['value'], _W[k]['status'], _W[k].get('source', '')))
    rows.append(('인터넷 범위(원/월)', DATA['internet']['range_won_per_month'], DATA['internet']['status'], DATA['internet']['source']))
    return rows
