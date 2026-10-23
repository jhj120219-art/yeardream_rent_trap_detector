# -*- coding: utf-8 -*-
"""마이크로데이터 분포표(data/utility_stats/micro_dist_seoul.csv, 로컬 전용)에서 사용자 조건에 맞는 집단을 골라 참고 분포를 돌려준다.
- 분포표가 없으면(저장소에는 올라가지 않음) None 을 돌려주고, 호출한 쪽은 기존 방식(조건별 평균 폭)을 쓴다.
- 선택 규칙: 조건에 가까운 집단부터 넓은 집단 순으로 훑어 status 가 DISPLAY 인 첫 집단을 기본으로 쓴다.
  그보다 구체적인 집단 중 EXPLORATORY 는 '탐색적 참고'로 따로 돌려주고, HIDDEN 은 이유만 알린다.
- 실제로 쓴 집단 이름을 반드시 함께 돌려준다(예: '1인 가구'를 '20㎡ 원룸 평균'처럼 표현하지 않기 위해)."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # 이 저장소에는 분포표(data/…)가 없어 기본은 None, 로컬에 있을 때만 사용

PATH = ROOT / 'data' / 'utility_stats' / 'micro_dist_seoul.csv'
_cache = None


def _load():
    global _cache
    if _cache is None:
        _cache = {}
        if PATH.exists():
            for r in csv.DictReader(open(PATH, encoding='utf-8-sig')):
                _cache[(r['segment'], r['kind'], int(r['month']), r['variant'])] = r
    return _cache


def available():
    return bool(_load())


def chain(household_size, area_band):
    """구체적 -> 넓은 순 집단 이름. area_band: '~33㎡' / '33~66㎡' / '66~99㎡'."""
    small = area_band == '~33㎡'
    if household_size == 1:
        return (['1인 & 33㎡ 미만'] if small else []) + (['1인 & 50㎡ 미만'] if area_band in ('~33㎡', '33~66㎡') else []) + ['1인 가구', '서울 전체']
    if household_size == 2:
        return (['1~2인 & 50㎡ 미만'] if area_band in ('~33㎡', '33~66㎡') else []) + ['서울 전체']
    return ['서울 전체']


def _num(r, k):
    return float(r[k]) if r.get(k) not in (None, '') else None


def pick(kind, month, household_size, area_band, variant='pos'):
    """kind: 'electric_kwh' / 'gas_nm3'(도시가스 난방 가구 기준). 돌려주는 값: main(기본), exploratory(탐색적), hidden(숨김 이유), tried(훑은 순서)."""
    data = _load()
    if not data:
        return None
    seg_suffix = ' (도시가스 난방)' if kind == 'gas_nm3' else ''
    main, expl, hidden, tried = None, [], [], []
    for seg in chain(household_size, area_band):
        r = data.get((seg, kind, month, variant))
        if not r:
            tried.append((seg, 'NONE')); continue
        tried.append((seg, r['status']))
        item = dict(segment=seg + seg_suffix, n=int(r['n']), n_eff=float(r['n_eff']), status=r['status'], variant=variant,
                    kwh_or_m3=dict(q25=_num(r, 'q25'), q50=_num(r, 'q50'), q75=_num(r, 'q75')),
                    bill=dict(q25=_num(r, 'bill_q25'), q50=_num(r, 'bill_q50'), q75=_num(r, 'bill_q75')),
                    bill_ci=dict(q25=(_num(r, 'bill_q25_lo'), _num(r, 'bill_q25_hi')), q50=(_num(r, 'bill_q50_lo'), _num(r, 'bill_q50_hi')), q75=(_num(r, 'bill_q75_lo'), _num(r, 'bill_q75_hi'))))
        if r['status'] == 'DISPLAY':
            main = item
            break
        (expl if r['status'] == 'EXPLORATORY' else hidden).append(item)
    return dict(main=main, exploratory=expl, hidden=[dict(segment=h['segment'], n=h['n'], n_eff=h['n_eff']) for h in hidden], tried=tried)

POOL_K = 40   # 사전 등록(과정기록 05 · docs/maintenance_validation.md)에서 정한 값. 데이터를 보고 바꾸지 않는다.


def pooled(kind, month, household_size, area_band, variant='pos', k=POOL_K):
    """부분 풀링 분위수(전기만 검증됨). 사슬(구체 -> 넓은 순)의 각 집단 로그 분위수를 부모 쪽으로 수축한다.
    가장 넓은 집단부터 w = n_eff / (n_eff + k) 로 theta = w * 자기 + (1 - w) * 부모(수축 후). 가구 단위 5-fold x10 반복 평가에서
    현재 방식(DISPLAY 집단까지 거슬러 올라감)보다 5개 소형 집단 매크로 pinball 이 12.3% 낮았고 Q25~Q75 포함률 49.3%, Q10~Q90 80.1%였다.
    검증은 2023 조사 가구의 사용량 분포 추정에 대한 것이며 실제 청구액 예측이 아니다. 요금은 사용량 분위수를 요금표로 환산(단조 변환)한다.
    분포표가 없거나 집단 정보가 부족하면 None."""
    if kind != 'electric_kwh':
        return None
    data = _load()
    if not data:
        return None
    import math
    rows = [(seg, data.get((seg, kind, month, variant))) for seg in chain(household_size, area_band)]
    rows = [(s, r) for s, r in rows if r and all(r.get(c) not in (None, '') for c in ('q10', 'q25', 'q50', 'q75', 'q90'))]
    if not rows:
        return None
    vec = lambda r: [math.log(float(r[c])) for c in ('q10', 'q25', 'q50', 'q75', 'q90')]
    theta = vec(rows[-1][1])
    for seg, r in reversed(rows[:-1]):
        w = float(r['n_eff']) / (float(r['n_eff']) + k)
        theta = [w * a + (1 - w) * b for a, b in zip(vec(r), theta)]
    theta.sort()
    from .calc import electricity_bill
    q = dict(zip(('q10', 'q25', 'q50', 'q75', 'q90'), (math.exp(t) for t in theta)))
    return dict(method='PARTIAL_POOLING', k=k, segments=[s for s, _ in rows], most_specific=rows[0][0],
                n=int(rows[0][1]['n']), n_eff=float(rows[0][1]['n_eff']),
                kwh_or_m3={n: round(q[n], 1) for n in ('q25', 'q50', 'q75')},
                bill={n: electricity_bill(q[n], month)['total'] for n in ('q25', 'q50', 'q75')})
