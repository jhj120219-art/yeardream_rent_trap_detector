#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""개선 여지(headroom) 점검 — 설계 데이터(6개 구)에서만 수행. 홀드아웃 데이터는 사용하지 않는다.

(A) 머신러닝(HistGradientBoosting, 분위수 손실)이 현재 규칙 기반 비교(1~3차 중앙값)보다 오차가 얼마나 작은가?
    - 학습: 기준 기간(최근 3개월) 이전 신규 월세 계약 / 평가: 설계 백테스트와 같은 기준 매물 8,995건
    - 공정 비교를 위해 규칙 기반도 '같은 학습 기간 이전 거래만 쓰는 버전'을 함께 계산
(B) '같은 건물(같은 지번)' 거래를 가장 먼저 비교하는 0단계를 추가하면 정확도가 오르는가? (아파트·연립다세대·오피스텔; 단독다가구는 지번 없음)
실행: python exp_headroom.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / '_libs'))
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
import compare_rent as cr

HERE = Path(__file__).parent
OUT = HERE / 'output'
rent = pd.read_csv(OUT / 'clean_rent_data.csv', parse_dates=['date'], low_memory=False, dtype={'MNO': str, 'SNO': str, 'STDG_CD': str, 'CGG_CD': str})
for c in ('is_new', 'basement', 'dup_suspect'):
    rent[c] = rent[c].astype(bool)
new = rent[rent['is_new']].copy()
# 설계 백테스트와 동일한 기준 매물(run_validation.py 와 같은 방식·시드)
_parts = []
for _, g in new.groupby('gu'):
    g = g[g['date'] >= g['date'].max() - pd.DateOffset(months=3)]
    _parts.append(g.sample(min(1500, len(g)), random_state=7))
bases = pd.concat(_parts)
bt = pd.read_csv(OUT / 'backtest_all.csv')
assert len(bt) == len(bases) and np.allclose(bt['actual'].values, bases['rent'].values), '기준 매물 정렬 불일치'
bases = bases.reset_index(drop=True)
bt['rule_pred'] = bt['median']
bt['rule_err'] = (bt['median'] - bt['actual']).abs() / bt['actual']
cut = new['date'].max() - pd.DateOffset(months=3)
print('학습/기준 경계일:', cut.date(), '| 기준 매물', len(bases))

# ------------------------------------------------------------ (A) 머신러닝
t0 = new['date'].min()
USAGE_CODE = {u: i for i, u in enumerate(cr.USAGES)}
GU_CODE = {g: i for i, g in enumerate(sorted(new['gu'].unique()))}
dong_codes = {k: i for i, k in enumerate(sorted(set(zip(new['gu'], new['dong']))))}


def feats(df):
    X = pd.DataFrame({
        'usage': df['usage'].map(USAGE_CODE), 'gu': df['gu'].map(GU_CODE),
        'dong': [dong_codes.get(k, -1) for k in zip(df['gu'], df['dong'])],
        'area': df['area'].values, 'dep': np.log1p(df['dep'].values), 'arch': df['arch'].values,
        'flr': df['flr'].values, 'basement': df['basement'].astype(int).values,
        't': (df['date'] - t0).dt.days.values})
    return X


train = new[new['date'] < cut]
Xtr, ytr = feats(train), np.log(train['rent'].values)
Xte = feats(bases)
res = {}
for q in (0.25, 0.5, 0.75):
    m = HistGradientBoostingRegressor(loss='quantile', quantile=q, max_iter=300, learning_rate=0.08, max_leaf_nodes=48,
                                      categorical_features=[0, 1, 2], random_state=0)
    m.fit(Xtr, ytr)
    res[q] = np.exp(m.predict(Xte))
bt['ml_pred'] = res[0.5]
bt['ml_err'] = (bt['ml_pred'] - bt['actual']).abs() / bt['actual']
bt['ml_in_iqr'] = (bt['actual'] >= np.minimum(res[0.25], res[0.75])) & (bt['actual'] <= np.maximum(res[0.25], res[0.75]))

# 공정 비교: 규칙 기반도 학습 경계일 이전 거래만 사용
rent_pre = rent[rent['date'] < cut]
pool_pre = cr.Pool(rent_pre)
rows = []
for r in bases.itertuples(index=False):
    L = dict(gu=r.gu, dong=r.dong, usage=r.usage, area=float(r.area), deposit=float(r.dep), rent=float(r.rent),
             arch_year=None if pd.isna(r.arch) else float(r.arch), basement=bool(r.basement))
    res_p = cr.compare(L, pool_pre, as_of=cut)
    rows.append(res_p['median'] if res_p['status'] == 'ok' else np.nan)
bt['rule_pre_pred'] = rows
bt['rule_pre_err'] = (bt['rule_pre_pred'] - bt['actual']).abs() / bt['actual']


def line(name, e):
    e = pd.Series(e).dropna()
    return f'{name}: 중앙 오차 {100*e.median():.1f}%, 오차≤20% {100*(e<=.2).mean():.1f}%, 평균 오차 {100*e.mean():.1f}% (n={len(e)})'


print('\n=== (A) 전체 ===')
print(line('규칙 기반(현재, 직전 모든 거래 사용)', bt['rule_err']))
print(line('규칙 기반(학습 경계일 이전만)      ', bt['rule_pre_err']))
print(line('머신러닝 HGB(경계일 이전 학습)     ', bt['ml_err']))
print('ML 사분위 구간 포함률(기대 50%%): %.1f%%' % (100 * bt['ml_in_iqr'].mean()))
tab = []
for u in cr.USAGES:
    g = bt[bt['usage'] == u]
    tab.append({'용도': u, '규칙(현재) 중앙오차%': round(100 * g['rule_err'].median(), 1), '규칙(경계일 이전) 중앙오차%': round(100 * g['rule_pre_err'].median(), 1),
                'ML 중앙오차%': round(100 * g['ml_err'].median(), 1), 'ML ≤20%': round(100 * (g['ml_err'] <= .2).mean(), 1),
                '규칙(현재) ≤20%': round(100 * (g['rule_err'] <= .2).mean(), 1)})
tab = pd.DataFrame(tab)
print(tab.to_string(index=False))
# 신뢰도 높음/낮음 구간에서 ML 이 더 나은가
for gr in ('높음', '보통', '낮음'):
    g = bt[bt['grade'] == gr]
    print(f'  등급 {gr}: 규칙 {100*g["rule_err"].median():.1f}% vs ML {100*g["ml_err"].median():.1f}%  (n={len(g)})')
for st in ('1차', '2차', '3차'):
    g = bt[bt['stage'] == st]
    print(f'  단계 {st}: 규칙 {100*g["rule_err"].median():.1f}% vs ML {100*g["ml_err"].median():.1f}%  (n={len(g)})')
# 규칙과 ML 의 평균(앙상블)
bt['ens_err'] = (((bt['rule_pred'] + bt['ml_pred']) / 2) - bt['actual']).abs() / bt['actual']
print(line('규칙·ML 평균(앙상블)', bt['ens_err']))
tab.to_csv(OUT / 'exp_headroom_ml.csv', index=False, encoding='utf-8-sig')

# ------------------------------------------------------------ (B) 같은 건물(지번) 0단계
new['lot'] = new['gu'] + '|' + new['dong'] + '|' + new['MNO'].fillna('').astype(str) + '|' + new['SNO'].fillna('').astype(str)
has_lot = new['MNO'].notna() & new['SNO'].notna()
lot_groups = {k: g.sort_values('date') for k, g in new[has_lot].groupby('lot')}
out = []
for i, r in enumerate(bases.itertuples(index=False)):
    if r.usage == '단독다가구' or pd.isna(r.MNO) or pd.isna(r.SNO):
        continue
    g = lot_groups.get(f'{r.gu}|{r.dong}|{r.MNO}|{r.SNO}')
    if g is None:
        continue
    g = g[(g['date'] < r.date) & (g['date'] >= r.date - pd.Timedelta(days=730)) & ((g['area'] - r.area).abs() <= r.area * 0.15)
          & (g['basement'] == r.basement)]
    band = r.dep * 0.5 if r.dep >= 1000 else 500
    g = g[(g['dep'] - r.dep).abs() <= band]
    if len(g) >= 3:
        out.append(dict(i=i, usage=r.usage, n_same=len(g), same_pred=float(g['rent'].median()), actual=float(r.rent)))
B = pd.DataFrame(out)
if len(B):
    B['same_err'] = (B['same_pred'] - B['actual']).abs() / B['actual']
    B['rule_err'] = bt.loc[B['i'], 'rule_err'].values
    B['ml_err'] = bt.loc[B['i'], 'ml_err'].values
    print('\n=== (B) 같은 건물 0단계(3건 이상) ===')
    print(f'적용 가능 매물: {len(B)}건 / 아파트·연립다세대·오피스텔 기준 매물 {int(bases["usage"].isin(["아파트", "연립다세대", "오피스텔"]).sum())}건')
    for u, g in [('전체', B)] + list(B.groupby('usage')):
        print(f'  {u} (n={len(g)}): 같은 건물 {100*g["same_err"].median():.1f}% vs 규칙(현재) {100*g["rule_err"].median():.1f}% vs ML {100*g["ml_err"].median():.1f}%'
              f' | ≤20%: {100*(g["same_err"]<=.2).mean():.0f}% / {100*(g["rule_err"]<=.2).mean():.0f}% / {100*(g["ml_err"]<=.2).mean():.0f}%')
    B.to_csv(OUT / 'exp_headroom_same_building.csv', index=False, encoding='utf-8-sig')
else:
    print('같은 건물 3건 이상 매물 없음')
