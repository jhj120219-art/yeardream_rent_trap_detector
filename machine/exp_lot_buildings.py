#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0단계의 '같은 지번 = 같은 건물' 가정 점검 — 건축HUB 표제부로 지번 하나에 주건축물이 몇 동인지 확인한다.
설계 데이터(6개 구)의 0단계 적용 사례(exp_stage0_cases.csv)에서 지번 표본을 뽑아 조회, 건물 수별 0단계 오차를 비교.
키는 --key-file (출력하지 않음). 사용: python exp_lot_buildings.py --key-file KEY.txt --n-lots 400
"""
import argparse, re, sys, time
from pathlib import Path
from urllib.parse import unquote
sys.path.insert(0, str(Path(__file__).parent / '_libs'))
import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).parent
OUT = HERE / 'output'
BASE = 'http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo'
ap = argparse.ArgumentParser()
ap.add_argument('--key-file', required=True)
ap.add_argument('--n-lots', type=int, default=400)
ap.add_argument('--seed', type=int, default=5)
a = ap.parse_args()
key = re.findall(r'[A-Za-z0-9%+=/]{40,}', Path(a.key_file).read_text(encoding='utf-8'))[0]

S = pd.read_csv(OUT / 'exp_stage0_cases.csv')
S = S[S['n_dd'] >= 3].copy()
S['err_dd'] = (S['med_dd'] - S['actual']).abs() / S['actual']
rent = pd.read_csv(OUT / 'clean_rent_data.csv', usecols=['gu', 'dong', 'CGG_CD', 'STDG_CD', 'MNO', 'SNO'], dtype=str)
rent['lot'] = rent['gu'] + '|' + rent['dong'] + '|' + rent['MNO'].fillna('') + '|' + rent['SNO'].fillna('')
codes = rent.drop_duplicates('lot').set_index('lot')[['CGG_CD', 'STDG_CD', 'MNO', 'SNO']]
lots = S.drop_duplicates('lot')[['lot', 'usage']]
rng = np.random.default_rng(a.seed)
pick = lots.iloc[rng.permutation(len(lots))[:a.n_lots]]
sess = requests.Session()
res = []
for n, r in enumerate(pick.itertuples(index=False)):
    c = codes.loc[r.lot]
    params = {'serviceKey': unquote(key), 'sigunguCd': c['CGG_CD'], 'bjdongCd': c['STDG_CD'], 'platGbCd': '0',
              'bun': str(c['MNO']).zfill(4), 'ji': str(c['SNO']).zfill(4), 'numOfRows': 100, 'pageNo': 1, '_type': 'json'}
    items = None
    for t in range(3):
        try:
            j = sess.get(BASE, params=params, timeout=40).json()['response']['body']
            it = (j.get('items') or {})
            it = it.get('item') if isinstance(it, dict) else None
            items = [] if it is None else (it if isinstance(it, list) else [it])
            break
        except Exception:
            time.sleep(1.5)
    if items is None:
        res.append(dict(lot=r.lot, ok=False))
        continue
    main = [x for x in items if str(x.get('mainAtchGbCd')) == '0']
    res.append(dict(lot=r.lot, ok=True, n_total=len(items), n_main=len(main),
                    purposes='/'.join(sorted({str(x.get('mainPurpsCdNm')) for x in main}))))
    if n % 50 == 0:
        print(n, '조회', flush=True)
    time.sleep(0.12)
R = pd.DataFrame(res)
R.to_csv(OUT / 'exp_lot_buildings_raw.csv', index=False, encoding='utf-8-sig')
R = R[R['ok']]
print('조회 성공', len(R), '/', len(pick), '| 주건축물 0동(대장에서 못 찾음):', int((R['n_main'] == 0).sum()))
A = S.merge(R, on='lot')
A['bgrp'] = pd.cut(A['n_main'], [-1, 0, 1, 2, 5, 10 ** 6], labels=['0동(미확인)', '1동', '2동', '3~5동', '6동+'])
print('\n지번 내 주건축물 수별 0단계(중복제거 n>=3) vs 기존 중앙 오차 (%)')
for g, x in A.groupby('bgrp', observed=True):
    print(f'  {g}: 지번 {x["lot"].nunique()}곳, 사례 {len(x)}건 | 0단계 {100*x["err_dd"].median():.1f} / 기존 {100*x["rule_err"].median():.1f} | '
          f'건물명 2개+ 비율 {100*(x["n_names"]>=2).mean():.0f}%')
A['single'] = A['n_main'] == 1
x1, x2 = A[A['n_main'] == 1], A[A['n_main'] >= 2]
print(f'\n1동 지번: 0단계 {100*x1["err_dd"].median():.1f}% / 기존 {100*x1["rule_err"].median():.1f}%  (n={len(x1)})')
print(f'2동+ 지번: 0단계 {100*x2["err_dd"].median():.1f}% / 기존 {100*x2["rule_err"].median():.1f}%  (n={len(x2)})')
print('건물명 수와 대장 동수의 일치: 건물명 2개+ 중 대장 2동+ 비율 %.0f%%, 건물명 1개 중 대장 2동+ 비율 %.0f%%' % (
    100 * (A[A['n_names'] >= 2]['n_main'] >= 2).mean(), 100 * (A[A['n_names'] == 1]['n_main'] >= 2).mean()))
