# -*- coding: utf-8 -*-
"""요금 기준 데이터 시험: (1) 원본 JSON 스키마(모든 값에 status, 출처 또는 가정 사유) (2) 로더가 이전 코드 상수와 같은 값을 만드는지(회귀)
(3) 확인 상태가 VERIFIED 가 아닌 값이 계산 결과의 assumptions 에 표시되는지 (4) 수도 앵커(10㎥=13,380원).
사용: python -m utility.test_tariff_data (analysis_internal 에서)"""
import json
import sys

from .calc import electricity_bill, gas_bill, water_bill
from . import tariffs as T

# 2026-10-20 정형화 이전 tariffs.py 에 하드코딩돼 있던 값(회귀 기준)
PREV = dict(
    tiers_summer=[(300, 910, 120.0), (450, 1600, 214.6), (None, 7300, 307.3)],
    tiers_other=[(200, 910, 120.0), (400, 1600, 214.6), (None, 7300, 307.3)],
    fuel=5.0, climate=9.0, fund=0.027, vat=0.10, gas=(22.5268, 1250, 42.6, 1.0), water=(1080, 580, 480, 170))   # 열량은 2026-10-21 가스공사 실적(12개월 평균 42.6)으로 갱신. 이전 가정값 43.0


def main():
    bad = []
    d = json.loads(T.DATA_PATH.read_text(encoding='utf-8'))
    if d.get('schema_version') != 'tariff-v1':
        bad.append('schema_version')
    legend = set(d['status_legend'])

    def walk(o, path=''):
        if isinstance(o, dict):
            if 'status' in o and 'value' in o:
                if o['status'] not in legend:
                    bad.append(f'status 값 오류 {path}')
                if o['status'] != 'VERIFIED' and not (o.get('note') or o.get('source')):
                    bad.append(f'미확인 값에 사유 없음 {path}')
                if o['status'] == 'VERIFIED' and not o.get('source'):
                    bad.append(f'VERIFIED 인데 출처 없음 {path}')
            for k, v in o.items():
                walk(v, path + '/' + k)
    walk(d)
    E, G, W = T.ELECTRIC, T.GAS, T.WATER
    if E['tiers_summer'] != PREV['tiers_summer'] or E['tiers_other'] != PREV['tiers_other']:
        bad.append('전기 구간 회귀')
    if (E['fuel_adjust_won_per_kwh'], E['climate_won_per_kwh'], E['fund_rate'], E['vat_rate']) != (PREV['fuel'], PREV['climate'], PREV['fund'], PREV['vat']):
        bad.append('전기 구성요소 회귀')
    if (G['won_per_mj'], G['base_won_per_month'], G['mj_per_nm3'], G['correction']) != PREV['gas']:
        bad.append('가스 회귀')
    if (W['base_won_per_month_15mm'], W['waterworks_won_per_m3'], W['sewerage_won_per_m3'], W['water_use_charge_won_per_m3']) != PREV['water']:
        bad.append('수도 회귀')
    if water_bill(10)['total'] != 13380:
        bad.append('수도 앵커')
    a = electricity_bill(250, 10)['assumptions']
    if sorted(a) != ['climate', 'fund']:
        bad.append(('전기 가정 표시', a))
    if gas_bill(30)['assumptions'] != []:      # 열량이 VERIFIED 가 되어 가스 계산에 남은 미확인 가정 표시가 없어야 함(온압보정계수는 별도 가정으로 note 에만 있음)
        bad.append(('가스 가정 표시', gas_bill(30)['assumptions']))
    print(f'요금 기준 {T.TARIFF_SET_ID}: 항목 {len(T.status_table())}개, 위반 {len(bad)}건')
    for st in ('VERIFIED', 'PARTIAL', 'ASSUMPTION'):
        print(f'  {st}: {sum(1 for r in T.status_table() if r[2] == st)}개')
    for b in bad:
        print('  ', b)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
