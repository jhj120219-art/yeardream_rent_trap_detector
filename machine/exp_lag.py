#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""신고 지연 민감도 — 설계 데이터(6개 구). 평가 계약일보다 L일 앞선 시점(as_of = 계약일 - L)까지의 거래만으로 기존 1~3차 규칙을 실행한다.
(비교 창도 L일 앞당겨지므로, 실제 '공개 지연'을 완전히 재현하는 것은 아니고 보수적인 근사다.)
실행: python exp_lag.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / '_libs'))
import numpy as np
import pandas as pd
import compare_rent as cr

HERE = Path(__file__).parent
OUT = HERE / 'output'
rent = pd.read_csv(OUT / 'clean_rent_data.csv', parse_dates=['date'], low_memory=False,
                   dtype={'MNO': str, 'SNO': str, 'STDG_CD': str, 'CGG_CD': str})
for c in ('is_new', 'basement', 'dup_suspect'):
    rent[c] = rent[c].astype(bool)
new = rent[rent['is_new']]
parts = []
for _, g in new.groupby('gu'):
    g = g[g['date'] >= g['date'].max() - pd.DateOffset(months=3)]
    parts.append(g.sample(min(1500, len(g)), random_state=7))
bases = pd.concat(parts).reset_index(drop=True)
pool = cr.Pool(rent)

res = {}
for L in (0, 30, 45, 60):
    rows = []
    for r in bases.itertuples(index=False):
        listing = dict(gu=r.gu, dong=r.dong, usage=r.usage, area=float(r.area), deposit=float(r.dep), rent=float(r.rent),
                       arch_year=None if pd.isna(r.arch) else float(r.arch), basement=bool(r.basement))
        o = cr.compare(listing, pool, as_of=r.date - pd.Timedelta(days=L))
        if o['status'] == 'ok':
            rows.append((o['stage'], o['median'], o['trust']['grade'] if 'trust' in o else None))
        else:
            rows.append((None, np.nan, None))
    d = pd.DataFrame(rows, columns=['stage', 'pred', 'grade'])
    d['err'] = (d['pred'] - bases['rent'].values).abs() / bases['rent'].values
    res[L] = d
    print(f'지연 {L:>2}일: 판정 가능 {d["pred"].notna().sum()}건, 중앙 오차 {100*d["err"].median():.2f}%, <=20% {100*(d["err"]<=.2).mean():.1f}%, '
          f'단계 분포 {d["stage"].value_counts().to_dict()}')
    for u in cr.USAGES:
        m = (bases['usage'] == u).values
        print(f'    {u}: {100*d.loc[m, "err"].median():.2f}%', end='')
    print()
pd.DataFrame({f'L{L}_err': d['err'] for L, d in res.items()}).to_csv(OUT / 'exp_lag_errors.csv', index=False, encoding='utf-8-sig')
