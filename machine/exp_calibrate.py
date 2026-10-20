#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""신뢰도 점수 보정 실험 — 설계 6개 구 백테스트(output/backtest_all.csv)만 사용. 홀드아웃 미사용.
질문: (1) 현재 등급(높음/보통/낮음)이 실제 오차 순서와 맞는가? (2) 비교 건수·분포 폭 등으로 '오차 20% 이내일 확률'을 구 단위 교차검증으로
예측하면 현재 점수보다 구분력(AUC)·보정(calibration)이 좋은가? (3) 구간(Q25~Q75, Q10~Q90) 실제 포함률은?
실행: python exp_calibrate.py
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
bt = pd.read_csv(OUT / 'backtest_all.csv')
bt = bt[bt['status'].astype(str).str.contains('ok|정상', regex=True) | bt['err'].notna()].dropna(subset=['err', 'median', 'q25', 'q75']).reset_index(drop=True)
bt['ok20'] = (bt['err'] <= 0.20).astype(int)
bt['ok10'] = (bt['err'] <= 0.10).astype(int)
bt['iqr'] = (bt['q75'] - bt['q25']) / bt['median']
bt['iqr90'] = (bt['q90'] - bt['q10']) / bt['median']
bt['logn'] = np.log(bt['n'])
bt['stage_i'] = bt['stage'].str.extract(r'(\d)').astype(int)
print('n =', len(bt), '| 전체 중앙 오차 %.2f%% | <=20%% %.1f%%' % (100 * bt['err'].median(), 100 * bt['ok20'].mean()))

print('\n=== (1) 현재 등급별 실제 오차 ===')
order = ['높음', '보통', '낮음']
for g in order:
    x = bt[bt['grade'] == g]
    print(f'  {g}: n={len(x)} 중앙 {100*x["err"].median():.1f}% | <=20% {100*x["ok20"].mean():.1f}% | Q25~Q75 포함 {100*((x["actual"]>=x["q25"])&(x["actual"]<=x["q75"])).mean():.1f}%'
          f' | Q10~Q90 포함 {100*((x["actual"]>=x["q10"])&(x["actual"]<=x["q90"])).mean():.1f}%')
print('  용도별 × 등급 (<=20% 비율, n):')
for u, gu in bt.groupby('usage'):
    print('   ', u, ' / '.join(f'{g} {100*gu[gu["grade"]==g]["ok20"].mean():.0f}%({(gu["grade"]==g).sum()})' for g in order if (gu['grade'] == g).any()))
print('  단계별 (<=20%):', {s: f'{100*x["ok20"].mean():.0f}% (n={len(x)})' for s, x in bt.groupby('stage')})

print('\n=== (2) 구 단위 교차검증(leave-one-구-out): 오차<=20% 확률 예측 ===')
usage_d = pd.get_dummies(bt['usage'], prefix='u').astype(float)
X_all = pd.concat([bt[['logn', 'iqr', 'iqr90', 'stage_i', 'fit', 'suff']], usage_d], axis=1)
sets = {'현재 점수(fit+suff)': ['fit', 'suff'],
        '건수+분포폭': ['logn', 'iqr'],
        '건수+분포폭+단계': ['logn', 'iqr', 'iqr90', 'stage_i'],
        '건수+분포폭+단계+용도': ['logn', 'iqr', 'iqr90', 'stage_i'] + list(usage_d.columns),
        '전체': list(X_all.columns)}
pred = {}
for name, cols in sets.items():
    p = np.zeros(len(bt))
    for gu in bt['gu'].unique():
        te = (bt['gu'] == gu).values
        sc = StandardScaler().fit(X_all.loc[~te, cols])
        m = LogisticRegression(C=1.0, max_iter=1000).fit(sc.transform(X_all.loc[~te, cols]), bt.loc[~te, 'ok20'])
        p[te] = m.predict_proba(sc.transform(X_all.loc[te, cols]))[:, 1]
    pred[name] = p
    print(f'  {name:<22} AUC {roc_auc_score(bt["ok20"], p):.3f} | Brier {brier_score_loss(bt["ok20"], p):.4f}')
# 현재 점수 자체(보정 없이) AUC
cur = bt['fit'] + bt['suff']
print(f'  (참고) 현재 fit+suff 단순합 AUC {roc_auc_score(bt["ok20"], cur):.3f} | 현재 등급 서수(높음=2) AUC {roc_auc_score(bt["ok20"], bt["grade"].map({"높음":2,"보통":1,"낮음":0})):.3f}')
base = bt['ok20'].mean()
print(f'  (참고) 항상 {base:.3f} 예측 Brier {brier_score_loss(bt["ok20"], np.full(len(bt), base)):.4f}')

best = '건수+분포폭+단계+용도'
bt['p20'] = pred[best]
print(f'\n=== (3) 보정 확인: [{best}] 예측확률 구간별 실제 비율 ===')
bt['pbin'] = pd.cut(bt['p20'], [0, .3, .4, .5, .6, .7, .8, .9, 1.0])
for b, x in bt.groupby('pbin', observed=True):
    print(f'  예측 {b}: n={len(x)} 실제 <=20% {100*x["ok20"].mean():.1f}% (평균 예측 {100*x["p20"].mean():.1f}%) | 중앙 오차 {100*x["err"].median():.1f}%')

print('\n=== (4) 새 등급 후보: 예측확률 컷오프 ===')
for hi, mid in ((.75, .55), (.80, .60), (.70, .50)):
    g = np.where(bt['p20'] >= hi, '높음', np.where(bt['p20'] >= mid, '보통', '낮음'))
    s = []
    for lab in order:
        x = bt[g == lab]
        s.append(f'{lab} n={len(x)}({100*len(x)/len(bt):.0f}%) <=20% {100*x["ok20"].mean():.0f}% 중앙 {100*x["err"].median():.1f}%')
    print(f'  컷 {hi}/{mid}: ' + ' | '.join(s))
print('  (현재) ' + ' | '.join(f'{lab} n={(bt["grade"]==lab).sum()}({100*(bt["grade"]==lab).mean():.0f}%) <=20% {100*bt[bt["grade"]==lab]["ok20"].mean():.0f}% 중앙 {100*bt[bt["grade"]==lab]["err"].median():.1f}%' for lab in order))

# 구별 안정성
print('\n=== (5) 새 등급(.75/.55)의 구별 <=20% ===')
bt['newg'] = np.where(bt['p20'] >= .75, '높음', np.where(bt['p20'] >= .55, '보통', '낮음'))
print(bt.pivot_table(index='gu', columns='newg', values='ok20', aggfunc=lambda s: round(100 * s.mean())).reindex(columns=order).to_string())

# 모델 계수(전체 학습) — 설명용
sc = StandardScaler().fit(X_all[sets[best]])
m = LogisticRegression(C=1.0, max_iter=1000).fit(sc.transform(X_all[sets[best]]), bt['ok20'])
print('\n계수(표준화):', {c: round(float(w), 2) for c, w in zip(sets[best], m.coef_[0])})
bt.drop(columns=['pbin']).to_csv(OUT / 'exp_calibrate_scored.csv', index=False, encoding='utf-8-sig')
