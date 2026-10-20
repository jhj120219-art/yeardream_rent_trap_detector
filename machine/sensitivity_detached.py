#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""단독다가구 층 미확인 민감도 실험.

단독다가구는 실거래 데이터의 층이 전부 0이라 지하·반지하와 지상층 계약이 섞여 있다. 층 효과를 직접 측정할 수 없으므로
(A) 층 정보가 있는 연립다세대에서 '지하(층 -1) 월세 / 같은 조건 지상층 월세' 할인율을 측정해 현실적인 이동 폭의 근거로 삼고,
(B) 백테스트 기준 매물의 비교 분포를 ±5~30% 이동시켰을 때 가격 라벨이 얼마나 뒤집히는지 측정한다.
이 실험은 '판정 안정성'을 보는 것이지 단독다가구의 실제 층 효과나 오판율을 측정한 것이 아니다.

[실험 전에 정한 통과 기준(사후 조정 금지)]
 1) 지하 비율 p=20% 가정 시 지상층 매물에 생기는 비교 편향 = +p×d (d = (A)에서 측정한 중앙 할인율)
 2) 그 편향만큼 비교 분포가 이동해도, 기준 라벨이 UPPER_TAIL 인 매물의 70% 이상이 '높은 편 이상(UPPER_TAIL/UPPER_RANGE)'을 유지하면 안정적
 3) 신뢰도 '높음' 등급 안에서 기준을 만족하면 그 등급에 한해 판정 허용을 검토
실행: python sensitivity_detached.py   (output/backtest_all.csv, output/clean_rent_data.csv 필요)
"""
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
OUT = HERE / 'output'
rent = pd.read_csv(OUT / 'clean_rent_data.csv', parse_dates=['date'], low_memory=False)
for c in ('is_new', 'basement', 'dup_suspect'):
    rent[c] = rent[c].astype(bool)

# ------------------------------------------------------------------ (A) 지하 할인율 근거
mu = rent[(rent['usage'] == '연립다세대') & rent['is_new']].sort_values('date').reset_index(drop=True)
base_idx = mu.index[mu['flr'] < 0]
ratios = []
for i in base_idx:
    b = mu.loc[i]
    lo = b['date'] - pd.Timedelta(days=365)
    m = mu[(mu['flr'] >= 1) & (mu['dong'] == b['dong']) & (mu['gu'] == b['gu']) & (mu['date'] < b['date']) & (mu['date'] >= lo)]
    m = m[(m['area'] - b['area']).abs() <= b['area'] * 0.20]
    band = b['dep'] * 0.5 if b['dep'] >= 1000 else 500
    m = m[(m['dep'] - b['dep']).abs() <= band]
    if len(m) >= 5:
        ratios.append(dict(gu=b['gu'], dong=b['dong'], rent=b['rent'], comp_median=float(m['rent'].median()), n=len(m),
                           ratio=b['rent'] / float(m['rent'].median())))
ra = pd.DataFrame(ratios)
q = ra['ratio'].quantile([.10, .25, .5, .75, .90])
d_med = 1 - float(q[0.5])
proxy = pd.DataFrame({'항목': ['지하 신규 월세 중 비교 가능', '지하/지상 월세 비율 P10', 'P25', '중앙값', 'P75', 'P90', '중앙 할인율 d(1-중앙 비율)'],
                      '값': [f'{len(ra)}건 / {len(base_idx)}건', round(q[0.10], 3), round(q[0.25], 3), round(q[0.5], 3), round(q[0.75], 3),
                           round(q[0.90], 3), round(d_med, 3)]})
by_gu = ra.groupby('gu')['ratio'].agg(['size', 'median']).round(3).reset_index().rename(columns={'size': '건수', 'median': '중앙 비율'})
print('=== (A) 지하(층 -1) vs 같은 동·면적·보증금대 지상층 월세 비율 (연립다세대, 신규, 직전 12개월 비교 5건 이상)')
print(proxy.to_string(index=False)); print(by_gu.to_string(index=False))
proxy.to_csv(OUT / 'sensitivity_basement_proxy.csv', index=False, encoding='utf-8-sig')

# 지하 비율 가정별 지상층 매물에 생기는 비교 편향
rows = []
for p in (0.05, 0.10, 0.20, 0.30):
    rows.append({'단독다가구 중 지하 비율 가정': f'{int(p*100)}%', '지상층 매물의 비교 편향 +p×d': round(p * d_med, 3),
                 '지하 매물의 비교 편향 -(1-p)×d': round(-(1 - p) * d_med, 3)})
bias = pd.DataFrame(rows)
print('\n=== 지하 비율 가정별 비교 분포 편향 (실제 지하 비율은 모름: 가정값)'); print(bias.to_string(index=False))
bias.to_csv(OUT / 'sensitivity_bias_assumptions.csv', index=False, encoding='utf-8-sig')
ADOPT_SHIFT = 0.20 * d_med            # 사전 기준 1)

# ------------------------------------------------------------------ (B) 분포 이동 민감도
bt = pd.read_csv(OUT / 'backtest_all.csv')
bt = bt[bt['status'] == 'ok'].copy()


def label(actual, q90, q75, q25, grade, stage):
    if grade == '낮음' or stage == '3차':
        return 'UNRATED'
    if actual > q90 and grade == '높음':
        return 'UPPER_TAIL'
    if actual > q75:
        return 'UPPER_RANGE'
    if actual < q25:
        return 'LOWER_RANGE'
    return 'TYPICAL_RANGE'


def labels(df, s):
    f = 1 + s
    return np.array([label(a, q90 * f, q75 * f, q25 * f, g, st)
                     for a, q90, q75, q25, g, st in zip(df['actual'], df['q90'], df['q75'], df['q25'], df['grade'], df['stage'])])


SHIFTS = [-0.30, -0.20, -0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15, 0.20, 0.30]
HIGH = {'UPPER_TAIL', 'UPPER_RANGE'}


def table(df, name, grades=None):
    d = df if grades is None else df[df['grade'].isin(grades)]
    base = labels(d, 0.0)
    out = []
    for s in SHIFTS:
        L = labels(d, s)
        row = {'대상': name, '비교 분포 이동': f'{s:+.0%}', '매물 수': len(d), '라벨 변경률(%)': round(100 * (L != base).mean(), 1)}
        tail = base == 'UPPER_TAIL'
        hi = np.isin(base, list(HIGH))
        row['기준 UPPER_TAIL 수'] = int(tail.sum())
        row['UPPER_TAIL 유지(%)'] = round(100 * (L[tail] == 'UPPER_TAIL').mean(), 1) if tail.any() else None
        row['UPPER_TAIL → 높은 편 이상 유지(%)'] = round(100 * np.isin(L[tail], list(HIGH)).mean(), 1) if tail.any() else None
        row['UPPER_TAIL → 시세 범위 이하로 이동(%)'] = round(100 * (~np.isin(L[tail], list(HIGH))).mean(), 1) if tail.any() else None
        row['기준 높은 편 이상 수'] = int(hi.sum())
        row['높은 편 이상 유지(%)'] = round(100 * np.isin(L[hi], list(HIGH)).mean(), 1) if hi.any() else None
        nonhi = ~hi & (base != 'UNRATED')
        row['기준 비경고 → 새로 경고(%)'] = round(100 * np.isin(L[nonhi], list(HIGH)).mean(), 1) if nonhi.any() else None
        out.append(row)
    return pd.DataFrame(out)


dd = bt[bt['usage'] == '단독다가구']
res = [table(dd, '단독다가구 전체'), table(dd, '단독다가구 신뢰도 높음', ['높음']), table(dd, '단독다가구 신뢰도 보통', ['보통'])]
for u in ('오피스텔', '아파트', '연립다세대'):
    res.append(table(bt[bt['usage'] == u], f'{u}(참고) 전체'))
allres = pd.concat(res, ignore_index=True)
allres.to_csv(OUT / 'sensitivity_detached_shift.csv', index=False, encoding='utf-8-sig')
base_dist = pd.Series(labels(dd, 0.0)).value_counts(normalize=True).mul(100).round(1)
print('\n=== (B) 기준 라벨 분포(단독다가구, 판정 허용 가정):', base_dist.to_dict())
cols = ['대상', '비교 분포 이동', '매물 수', '라벨 변경률(%)', '기준 UPPER_TAIL 수', 'UPPER_TAIL 유지(%)',
        'UPPER_TAIL → 높은 편 이상 유지(%)', '높은 편 이상 유지(%)', '기준 비경고 → 새로 경고(%)']
for name in allres['대상'].unique():
    print('\n--', name)
    print(allres[allres['대상'] == name][cols[1:]].to_string(index=False))

# ------------------------------------------------------------------ 사전 기준 평가
print('\n=== 사전 기준 평가 (채택 이동폭 = 20%% × d = %+.1f%%)' % (100 * ADOPT_SHIFT))
for name, grades in (('단독다가구 전체', None), ('단독다가구 신뢰도 높음', ['높음'])):
    d = dd if grades is None else dd[dd['grade'].isin(grades)]
    base = labels(d, 0.0); L = labels(d, ADOPT_SHIFT)
    tail = base == 'UPPER_TAIL'
    keep = np.isin(L[tail], list(HIGH)).mean() if tail.any() else float('nan')
    print(f'{name}: 기준 UPPER_TAIL {tail.sum()}건 중 +{ADOPT_SHIFT:.1%} 이동 후 높은 편 이상 유지 {100*keep:.1f}%  -> ',
          '통과(≥70%)' if keep >= 0.70 else '미달(<70%)')
