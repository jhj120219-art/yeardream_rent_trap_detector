# -*- coding: utf-8 -*-
"""최근 공공데이터 요약 시험: 12개월 모두 값 존재, 보정 미적용 표시, 요금 단조성(사용량 큰 달이 요금도 큼), 판정 용어 없음, 레지스트리 상태값.
사용: python test_recent.py (utility 폴더에서)"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from utility import recent_ref

FORBID = ['부당', '바가지', '과다 청구', '폭리', '사기', '정상 관리비', '적정']


def main():
    bad = []
    if not recent_ref.available():
        print('요약 없음 — recent_load 를 먼저 실행'); return 1
    el = [recent_ref.electricity_recent(m) for m in range(1, 13)]
    gs = [recent_ref.gas_recent(m) for m in range(1, 13)]
    if any(x is None for x in el): bad.append('전기 12개월 누락')
    if any(x is None for x in gs): bad.append('가스 12개월 누락')
    if not bad:
        if any(x['adjustment_applied'] for x in el + gs): bad.append('보정 미적용 표시가 아님')
        pairs = sorted((x['kwh_per_customer'], x['bill_at_tariff_2026_10']) for x in el)
        # 여름(7·8월) 누진 구간이 달라 월 사이 단조성은 같은 계절 안에서만 확인
        for season, months in (('summer', (7, 8)), ('other', (1, 2, 3, 4, 5, 6, 9, 10, 11, 12))):
            ps = sorted((el[m - 1]['kwh_per_customer'], el[m - 1]['bill_at_tariff_2026_10']) for m in months)
            if any(b2 < b1 for (_, b1), (_, b2) in zip(ps, ps[1:])): bad.append(f'전기 요금 단조성 위반({season})')
        if not (0.8 < el[9]['kwh_per_customer'] / el[11]['kwh_per_customer'] < 1.3): bad.append('10월/12월 전기 비율 이상')
        if not -0.5 < gs[0]['yoy_annual_change'] < 0.5: bad.append('가스 연간 변화율 범위 이상')
        if gs[0]['bill_at_tariff_2026_10'] <= gs[7]['bill_at_tariff_2026_10']: bad.append('가스 1월 요금이 8월 이하')
    w = recent_ref.water_recent()
    if w is None: bad.append('수도 요약 누락')
    else:
        if abs(w['l_per_capita_day_reported'] - w['l_per_capita_day_computed']) > 0.5: bad.append('수도: 공식 1인1일 값과 부과량/급수인구/365 불일치')
        if w['adjustment_applied']: bad.append('수도: 보정 미적용 표시가 아님')
        if w['tariff_matches_first_m3'] is False: bad.append('수도: 요금표 단가가 공식 최초 1㎥ 요금과 다름')
        c = recent_ref.water_consistency({1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25})     # 합성 분포(형식 시험): 결과가 숫자이고 공식값과의 차이가 계산되는지
        if not c or abs(c['difference_pct']) > 60: bad.append('수도 일관성 계산 이상')
    snap = json.dumps(recent_ref.recent_snapshot(10), ensure_ascii=False)
    for w in FORBID:
        if w in snap: bad.append('판정 용어: ' + w)
    reg = json.loads(recent_ref.REGISTRY.read_text(encoding='utf-8'))
    for s in reg['sources']:
        if s['status'] not in ('VERIFIED', 'CANDIDATE', 'REJECTED'): bad.append('레지스트리 상태값: ' + s['source_id'])
    print('FAIL' if bad else 'PASS', bad if bad else '(전기·가스 12개월, 보정 미적용, 단조성, 용어, 레지스트리)')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
