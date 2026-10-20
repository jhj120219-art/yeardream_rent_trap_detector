#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0단계(같은 건물) 검증 — 설계 데이터(6개 구)에서만. 홀드아웃(서대문·성북·송파·강북) 미사용.
건수 기준(3/5/8/10), 중복 제거 유무, 소표본 축소추정(shrinkage), 기존 단계와의 불일치, 건물 단위 부트스트랩, 신고 지연(0/30/45/60일).
실행: python exp_stage0.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / '_libs'))
import numpy as np
import pandas as pd

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
bases['rule_pred'] = bt['median'].values
bases['rule_err'] = bt['err'].values
bases['grade'] = bt['grade'].values
bases['stage'] = bt['stage'].values

new['lot'] = new['gu'] + '|' + new['dong'] + '|' + new['MNO'].fillna('') + '|' + new['SNO'].fillna('')
has_lot = new['MNO'].notna() & new['SNO'].notna() & (new['usage'] != '단독다가구')
lots = {k: g.sort_values('date') for k, g in new[has_lot].groupby('lot')}
n_names = new[has_lot].groupby('lot')['BLDG_NM'].nunique()

rows = []
for i, r in bases.iterrows():
    if r.usage == '단독다가구' or pd.isna(r.MNO) or pd.isna(r.SNO):
        continue
    key = f'{r.gu}|{r.dong}|{r.MNO}|{r.SNO}'
    g0 = lots.get(key)
    if g0 is None:
        continue
    band = r.dep * 0.5 if r.dep >= 1000 else 500
    m = ((g0['date'] < r.date) & (g0['date'] >= r.date - pd.Timedelta(days=730)) & ((g0['area'] - r.area).abs() <= r.area * 0.15)
         & (g0['basement'] == r.basement) & ((g0['dep'] - r.dep).abs() <= band))
    g = g0[m]
    if len(g) == 0:
        continue
    gd = g.drop_duplicates(subset=['date', 'area', 'dep', 'rent', 'flr'])
    row = dict(i=i, lot=key, usage=r.usage, grade=r.grade, stage=r.stage, actual=r.rent, rule_pred=r.rule_pred, rule_err=r.rule_err,
               n_raw=len(g), n_dd=len(gd), n_dates=gd['date'].nunique(), n_names=int(n_names.get(key, 1)),
               med_raw=g['rent'].median(), med_dd=gd['rent'].median(),
               iqr_dd=(gd['rent'].quantile(.75) - gd['rent'].quantile(.25)) / max(gd['rent'].median(), 1),
               span_days=(r.date - g['date'].min()).days, last_gap=(r.date - g['date'].max()).days)
    # 신고 지연: 평가일 L일 이전 거래만 사용
    for L in (30, 45, 60):
        gl = gd[gd['date'] < r.date - pd.Timedelta(days=L)]
        row[f'n_L{L}'] = len(gl)
        row[f'med_L{L}'] = gl['rent'].median() if len(gl) else np.nan
    rows.append(row)
S = pd.DataFrame(rows)
S.to_csv(OUT / 'exp_stage0_cases.csv', index=False, encoding='utf-8-sig')
S['err_raw'] = (S['med_raw'] - S['actual']).abs() / S['actual']
S['err_dd'] = (S['med_dd'] - S['actual']).abs() / S['actual']
base_all = bases[bases['usage'] != '단독다가구']
print(f'기준 매물 {len(bases)}건, 지번 있는 비단독 {int(base_all[["MNO","SNO"]].notna().all(axis=1).sum())}건, 같은 건물 후보 1건 이상 {len(S)}건')


def med(x):
    return 100 * float(np.nanmedian(np.asarray(x, dtype=float))) if len(x) else float("nan")


def auto(N, col_n, col_med):
    """n>=N 이면 0단계 중앙값, 아니면 기존 규칙 -> 전체 8,995건 오차"""
    use = S[S[col_n] >= N]
    err = bases['rule_err'].copy().values
    err[use['i'].values] = ((use[col_med] - use['actual']).abs() / use['actual']).values
    return use, err


print('\n=== (1) 건수 기준 x 중복제거 (자동 전환: 0단계 충족 시 0단계, 아니면 기존) ===')
print(f'전체 기존 규칙: 중앙 {med(bases["rule_err"]):.2f}%, <=20% {100*(bases["rule_err"]<=.2).mean():.1f}%')
tab = []
for dd, cn, cm in (('원본', 'n_raw', 'med_raw'), ('중복제거', 'n_dd', 'med_dd')):
    for N in (3, 5, 8, 10):
        use, err = auto(N, cn, cm)
        e0 = ((use[cm] - use['actual']).abs() / use['actual'])
        tab.append({'중복': dd, '최소건수': N, '적용건수': len(use), '적용률(%)': round(100 * len(use) / len(bases), 1),
                    '적용건 0단계 중앙오차%': round(med(e0), 2), '적용건 기존 중앙오차%': round(med(use['rule_err']), 2),
                    '전체 자동전환 중앙오차%': round(med(err), 2), '전체 <=20%': round(100 * (err <= .2).mean(), 1),
                    '적용 건물수': use['lot'].nunique()})
T1 = pd.DataFrame(tab)
print(T1.to_string(index=False))
T1.to_csv(OUT / 'exp_stage0_thresholds.csv', index=False, encoding='utf-8-sig')

print('\n=== (1b) 용도별 (중복제거, N=5) ===')
use = S[S['n_dd'] >= 5]
for u, g in use.groupby('usage'):
    print(f'  {u}: n={len(g)} 0단계 {med(g["err_dd"]):.1f}% vs 기존 {med(g["rule_err"]):.1f}%')

print('\n=== (2) 소표본 축소추정: w=n/(n+k), 로그 월세에서 혼합 (n=중복제거 건수) ===')
tab = []
for k in (0, 1, 2, 3, 5, 10, 20):
    for nmin in (1, 3):
        g = S[S['n_dd'] >= nmin]
        w = g['n_dd'] / (g['n_dd'] + k) if k > 0 else 1.0
        p = np.exp(w * np.log(g['med_dd']) + (1 - w) * np.log(g['rule_pred'].fillna(g['med_dd'])))
        e = (p - g['actual']).abs() / g['actual']
        tab.append({'k': k, '최소건수': nmin, 'n': len(g), '축소추정 중앙오차%': round(med(e), 2), '기존 중앙오차%': round(med(g['rule_err']), 2),
                    '0단계 단독 중앙오차%': round(med(g['err_dd']), 2), '<=20%': round(100 * (e <= .2).mean(), 1)})
T2 = pd.DataFrame(tab)
print(T2.to_string(index=False))
T2.to_csv(OUT / 'exp_stage0_shrinkage.csv', index=False, encoding='utf-8-sig')
print('  건수 구간별 (k=3):')
for lo, hi in ((1, 2), (3, 4), (5, 9), (10, 10 ** 6)):
    g = S[(S['n_dd'] >= lo) & (S['n_dd'] <= hi)]
    if not len(g):
        continue
    w = g['n_dd'] / (g['n_dd'] + 3)
    p = np.exp(w * np.log(g['med_dd']) + (1 - w) * np.log(g['rule_pred'].fillna(g['med_dd'])))
    e = (p - g['actual']).abs() / g['actual']
    print(f'   n_dd {lo}~{hi if hi < 1e5 else "+"}: n={len(g)} 0단계 {med(g["err_dd"]):.1f}% / 축소 {med(e):.1f}% / 기존 {med(g["rule_err"]):.1f}%')

print('\n=== (3) 기존 단계와의 불일치 (중복제거 n>=3) ===')
g = S[S['n_dd'] >= 3].copy()
g['gap'] = (g['med_dd'] / g['rule_pred'] - 1).abs()
g['bin'] = pd.cut(g['gap'], [-1, .05, .10, .15, .25, 10], labels=['<5%', '5~10%', '10~15%', '15~25%', '25%+'])
for b, x in g.groupby('bin', observed=True):
    print(f'  차이 {b}: n={len(x)} 0단계 {med(x["err_dd"]):.1f}% / 기존 {med(x["rule_err"]):.1f}%  (0단계가 더 나은 비율 {100*(x["err_dd"]<x["rule_err"]).mean():.0f}%)')

print('\n=== (4) 건물 식별 위험: 지번당 건물명 수 ===')
g = S[S['n_dd'] >= 3]
for lab, x in (('건물명 1개', g[g['n_names'] == 1]), ('건물명 2개 이상', g[g['n_names'] >= 2])):
    if len(x):
        print(f'  {lab}: n={len(x)} 0단계 {med(x["err_dd"]):.1f}% / 기존 {med(x["rule_err"]):.1f}%')
print('  계약일 집중도(서로 다른 계약일 수 / 건수):')
g = g.assign(dr=g['n_dates'] / g['n_dd'])
for lab, x in (('다양(>=0.8)', g[g['dr'] >= .8]), ('집중(<0.8)', g[g['dr'] < .8])):
    if len(x):
        print(f'  {lab}: n={len(x)} 0단계 {med(x["err_dd"]):.1f}% / 기존 {med(x["rule_err"]):.1f}%')
print('  원본 vs 중복제거 건수 차이가 있는 사례:', int((S['n_raw'] > S['n_dd']).sum()), '/', len(S))

print('\n=== (5) 건물 단위 부트스트랩 (중복제거 n>=5, 개선폭 = 기존 - 0단계 중앙오차, %p) ===')
g = S[S['n_dd'] >= 5]
rng = np.random.default_rng(0)
by = {k: x for k, x in g.groupby('lot')}
keys = list(by)
d = []
for _ in range(1000):
    sel = rng.choice(len(keys), len(keys))
    x = pd.concat([by[keys[j]] for j in sel])
    d.append(100 * (x['rule_err'].median() - x['err_dd'].median()))
print(f'  적용 {len(g)}건 / 건물 {len(keys)}곳: 개선폭 {np.mean(d):.2f}%p, 95% 구간 [{np.percentile(d,2.5):.2f}, {np.percentile(d,97.5):.2f}]')
cnt = g.groupby('lot').size()
print(f'  건물당 최대 사례 {cnt.max()}건, 상위 5개 건물 비중 {100*cnt.sort_values(ascending=False).head(5).sum()/len(g):.1f}%')
for lab, ks in (('사례 3건 이하 건물', cnt[cnt <= 3].index), ('사례 4건 이상 건물', cnt[cnt >= 4].index)):
    x = g[g['lot'].isin(ks)]
    if len(x):
        print(f'  {lab}: n={len(x)} 0단계 {med(x["err_dd"]):.1f}% / 기존 {med(x["rule_err"]):.1f}%')

print('\n=== (6) 신고 지연: 0단계 비교 거래를 평가일 L일 이전으로 제한 (중복제거) ===')
for N in (3, 5):
    print(f'  최소건수 {N}:')
    base_n = S[S['n_dd'] >= N]
    print(f'    지연 0일: 적용 {len(base_n)}건, 0단계 {med(base_n["err_dd"]):.2f}%')
    for L in (30, 45, 60):
        x = S[S[f'n_L{L}'] >= N]
        e = (x[f'med_L{L}'] - x['actual']).abs() / x['actual']
        print(f'    지연 {L}일: 적용 {len(x)}건({100*len(x)/max(len(base_n),1):.0f}%), 0단계 {med(e):.2f}% / 같은 사례 기존 {med(x["rule_err"]):.2f}%')
