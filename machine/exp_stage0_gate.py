#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0단계(건축HUB 단일 건물 게이트) 적용 + 신뢰도 재학습 — 설계 6개 구만. 홀드아웃 미사용.
입력: output/clean_rent_data.csv, output/backtest_all.csv, data/lot_buildings_cache.csv (collect_lot_buildings.py)
캐시에 없거나 조회 실패(ok=False)인 지번은 0단계를 쓰지 않는다(1동으로 간주 금지).
실행: python exp_stage0_gate.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / '_libs'))
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).parent
OUT = HERE / 'output'
rent = pd.read_csv(OUT / 'clean_rent_data.csv', parse_dates=['date'], low_memory=False,
                   dtype={'MNO': str, 'SNO': str, 'STDG_CD': str, 'CGG_CD': str})
for c in ('is_new', 'basement', 'dup_suspect'):
    rent[c] = rent[c].astype(bool)
new = rent[rent['is_new']].copy()
parts = []
for _, g in new.groupby('gu'):
    g = g[g['date'] >= g['date'].max() - pd.DateOffset(months=3)]
    parts.append(g.sample(min(1500, len(g)), random_state=7))
bases = pd.concat(parts).reset_index(drop=True)
bt = pd.read_csv(OUT / 'backtest_all.csv')
assert len(bt) == len(bases) and np.allclose(bt['actual'].values, bases['rent'].values)
ok = bt['err'].notna().values
bases['rule_pred'] = bt['median'].values
bases['rule_err'] = bt['err'].values
bases['stage_i'] = bt['stage'].str.extract(r'(\d)')[0].astype(float).values
bases['n_rule'] = bt['n'].values
bases['q25'], bases['q75'], bases['q10'], bases['q90'] = bt['q25'].values, bt['q75'].values, bt['q10'].values, bt['q90'].values
bases['grade'] = bt['grade'].values

cache = pd.read_csv(HERE / 'data' / 'lot_buildings_cache.csv', dtype=str)
cache = cache[cache['ok'] == 'True']
cache['n_main'] = cache['n_main'].astype(int)
nmain = {(a, b, c, d): n for a, b, c, d, n in zip(cache.CGG_CD, cache.STDG_CD, cache.MNO, cache.SNO, cache.n_main)}
print(f'캐시 지번 {len(nmain)}곳 (성공만)')

new['lot'] = new['CGG_CD'] + '|' + new['STDG_CD'] + '|' + new['MNO'].fillna('') + '|' + new['SNO'].fillna('')
has_lot = new['MNO'].notna() & new['SNO'].notna() & (new['usage'] != '단독다가구')
lots = {k: g.sort_values('date') for k, g in new[has_lot].groupby('lot')}

rows = []
for i, r in bases.iterrows():
    if r.usage == '단독다가구' or pd.isna(r.MNO) or pd.isna(r.SNO):
        continue
    key = f'{r.CGG_CD}|{r.STDG_CD}|{r.MNO}|{r.SNO}'
    g0 = lots.get(key)
    if g0 is None:
        continue
    band = r.dep * 0.5 if r.dep >= 1000 else 500
    m = ((g0['date'] < r.date) & (g0['date'] >= r.date - pd.Timedelta(days=730)) & ((g0['area'] - r.area).abs() <= r.area * 0.15)
         & (g0['basement'] == r.basement) & ((g0['dep'] - r.dep).abs() <= band))
    g = g0[m].drop_duplicates(subset=['date', 'area', 'dep', 'rent', 'flr'])
    if len(g) == 0:
        continue
    v = g['rent'].values
    rows.append(dict(i=i, lot=key, n0=len(g), n_dates=g['date'].nunique(), med0=float(np.median(v)),
                     q25_0=float(np.percentile(v, 25)), q75_0=float(np.percentile(v, 75)), q10_0=float(np.percentile(v, 10)), q90_0=float(np.percentile(v, 90)),
                     nmain=nmain.get((r.CGG_CD, r.STDG_CD, r.MNO, r.SNO), -1)))
S = pd.DataFrame(rows).set_index('i')
print(f'0단계 후보(중복제거 1건 이상) {len(S)}건 | 캐시에서 동수 확인된 사례 {(S.nmain >= 0).sum()}건 | 1동 {(S.nmain == 1).sum()}건 | 2동 이상 {(S.nmain >= 2).sum()}건')


def build(min_n, gate, min_dates=0):
    """새 탐색 구조의 예측/구간/단계를 만든다."""
    d = bases[['rule_pred', 'rule_err', 'stage_i', 'n_rule', 'q25', 'q75', 'q10', 'q90', 'usage', 'gu', 'rent']].copy()
    d['stage_new'] = d['stage_i']
    d['pred'] = d['rule_pred']
    d['n_use'] = d['n_rule']
    q = {c: d[c].copy() for c in ('q25', 'q75', 'q10', 'q90')}
    s = S[(S.n0 >= min_n) & (S.n_dates >= min_dates)]
    if gate:
        s = s[s.nmain == 1]
    idx = s.index
    d.loc[idx, 'stage_new'] = 0
    d.loc[idx, 'pred'] = s['med0']
    d.loc[idx, 'n_use'] = s['n0']
    for c, c0 in (('q25', 'q25_0'), ('q75', 'q75_0'), ('q10', 'q10_0'), ('q90', 'q90_0')):
        q[c].loc[idx] = s[c0]
    for c in q:
        d[c] = q[c]
    d['err'] = (d['pred'] - d['rent']).abs() / d['rent']
    d['applied'] = d.index.isin(idx)
    return d


def med(x):
    return 100 * float(np.nanmedian(np.asarray(x, dtype=float)))


print('\n=== (1) 게이트 × 최소건수 × 계약일 수 (전체 자동전환) ===')
print(f'기존: 중앙 {med(bases["rule_err"]):.2f}%, <=20% {100*(bases["rule_err"].fillna(9)<=.2).mean():.1f}%')
tab = []
for gate in (False, True):
    for mn in (3, 5, 10):
        for md in (0, 3):
            d = build(mn, gate, md)
            a = d[d.applied]
            tab.append({'동수게이트': gate, '최소건수': mn, '최소계약일수': md, '적용': int(d.applied.sum()),
                        '적용 0단계%': round(med(a['err']), 2), '적용 기존%': round(med(a['rule_err']), 2),
                        '전체 중앙오차%': round(med(d['err']), 2), '전체 <=20%': round(100 * (d['err'].fillna(9) <= .2).mean(), 1)})
T = pd.DataFrame(tab)
print(T.to_string(index=False))
T.to_csv(OUT / 'exp_stage0_gate_table.csv', index=False, encoding='utf-8-sig')

# --- 선택한 정책으로 신뢰도 재학습 (구 단위 교차검증)
USE = '건수+폭+단계+단일건물/다동' if len(sys.argv) > 1 and sys.argv[1] == 'nogate' else '건수+폭+단계(0~3)'
POL = dict(min_n=3, gate=(len(sys.argv) < 2 or sys.argv[1] != 'nogate'), min_dates=0)
d = build(**POL)
d = d.dropna(subset=['err', 'q25', 'q75', 'q10', 'q90', 'pred']).copy()
d['ok20'] = (d['err'] <= .2).astype(int)
d['iqr'] = (d['q75'] - d['q25']) / d['pred']
d['iqr90'] = (d['q90'] - d['q10']) / d['pred']
d['logn'] = np.log(d['n_use'])
print(f'\n=== (2) 신뢰도 재학습: 정책 {POL}, 대상 {len(d)}건, 0단계 적용 {int(d.applied.sum())}건 ===')
sets = {'건수+폭+단계(0~3)': ['logn', 'iqr', 'iqr90', 'stage_new'],
        '폭 제외(건수+단계)': ['logn', 'stage_new'],
        '건수+폭+단계+0단계더미': ['logn', 'iqr', 'iqr90', 'stage_new', 'is0'],
        '건수+폭+단계+단일건물/다동': ['logn', 'iqr', 'iqr90', 'stage_new', 'single', 'multi']}
d['is0'] = d['applied'].astype(float)
d['single'] = (d['applied'] & (S['nmain'].reindex(d.index) == 1)).astype(float)
d['multi'] = (d['applied'] & (S['nmain'].reindex(d.index) >= 2)).astype(float)
pred = {}
for name, cols in sets.items():
    p = np.zeros(len(d))
    for gu in d['gu'].unique():
        te = (d['gu'] == gu).values
        sc = StandardScaler().fit(d.loc[~te, cols])
        m = LogisticRegression(max_iter=1000).fit(sc.transform(d.loc[~te, cols]), d.loc[~te, 'ok20'])
        p[te] = m.predict_proba(sc.transform(d.loc[te, cols]))[:, 1]
    pred[name] = p
    print(f'  {name:<22} AUC {roc_auc_score(d["ok20"], p):.3f} | Brier {brier_score_loss(d["ok20"], p):.4f}')
d['p20'] = pred[USE]
print(f'  (참고) 이전 구조 AUC 0.743 / Brier 0.2055, 현재 점수 0.672 / 0.2236')
d['newg'] = np.where(d['p20'] >= .75, '높음', np.where(d['p20'] >= .55, '보통', '낮음'))
print('\n=== (3) 새 구조 등급(0.75/0.55) ===')
for g in ['높음', '보통', '낮음']:
    x = d[d.newg == g]
    print(f'  {g}: n={len(x)}({100*len(x)/len(d):.0f}%) 0단계 비율 {100*x.applied.mean():.0f}% | <=20% {100*x.ok20.mean():.1f}% | 중앙 {100*x.err.median():.1f}%')
print('  보정(예측구간별 실제):')
for lo, hi in ((0, .3), (.3, .5), (.5, .6), (.6, .7), (.7, .8), (.8, 1.01)):
    x = d[(d.p20 >= lo) & (d.p20 < hi)]
    if len(x):
        print(f'   예측 {lo:.1f}~{min(hi,1):.1f}: n={len(x)} 실제 {100*x.ok20.mean():.1f}% (예측 {100*x.p20.mean():.1f}%)')
print('  0단계 적용/비적용 내 등급 순서:')
for lab, x0 in (('적용', d[d.applied]), ('비적용', d[~d.applied])):
    print('   ', lab, ' / '.join(f'{g} {100*x0[x0.newg==g].ok20.mean():.0f}%({(x0.newg==g).sum()})' for g in ['높음', '보통', '낮음'] if (x0.newg == g).any()))
print('  구별 높음/보통/낮음 <=20%:')
print(d.pivot_table(index='gu', columns='newg', values='ok20', aggfunc=lambda s: round(100 * s.mean())).reindex(columns=['높음', '보통', '낮음']).to_string())
print('\n=== (4) 순환성: 실제 월세가 Q90 초과 비율 ===')
d['q90x'] = d['rent'] > d['q90']
print(f'  전체 {100*d.q90x.mean():.1f}% | 새 높음 {100*d[d.newg=="높음"].q90x.mean():.1f}% | 새 높음 아님 {100*d[d.newg!="높음"].q90x.mean():.1f}%')
# 폭 제외 모델에서의 같은 비율
d['p_nw'] = pred['폭 제외(건수+단계)']
hi_nw = d['p_nw'] >= d['p_nw'].quantile(1 - (d.newg == '높음').mean())
print(f'  폭 제외 모델에서 같은 비율(상위 {100*(d.newg=="높음").mean():.0f}%)만 "높음": Q90 초과 {100*d[hi_nw].q90x.mean():.1f}%, <=20% {100*d[hi_nw].ok20.mean():.1f}%')
# 기준 월세 +-10% 시 높음 x Q90 초과 판정 유지 (이미 초과한 사례만; 하향 시 유지율)
h = d[(d.newg == '높음') & d.q90x]
for s in (-.05, -.10):
    print(f'  높음×Q90초과 {len(h)}건 중 월세를 {int(s*100)}% 낮춰도 Q90 초과 유지: {100*(h.rent*(1+s) > h.q90).mean():.0f}%')
d.to_csv(OUT / 'exp_stage0_gate_scored.csv', index=False, encoding='utf-8-sig')
