#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""건축물대장(건축HUB) 건물 재고로 단독다가구의 지하 주거 비율 p를 추정한다.

서울시·국토부 단독다가구 실거래에는 지번이 없어 계약 단위 연결이 불가능하다. 대신 법정동 단위로 건축물대장 표제부를 무작위 표본 조회해
  (1) 다가구주택 건물 중 지하층이 있는 비율,
  (2) 층별개요(getBrFlrOulnInfo)로 지하층의 '주거 용도 면적' / 전체 주거 면적 비율
을 계산한다. 가구 수 ∝ 계약 수라고 가정한 근사이며, 실제 계약 중 지하 비율과 같다고 보장할 수 없다.
키: --key-file(txt, 40자 이상 영숫자 첫 토큰). 키는 출력하지 않는다.
사용: python ledger_stock_p.py --key-file key.txt --gu 11620 --dongs 10100 10200 10300 --pages 8 --max-buildings 150
"""
import argparse, random, re, sys, time
from pathlib import Path
from urllib.parse import unquote
import pandas as pd
import requests

BASE = 'http://apis.data.go.kr/1613000/BldRgstHubService/'
ap = argparse.ArgumentParser()
ap.add_argument('--key-file', required=True); ap.add_argument('--gu', required=True); ap.add_argument('--dongs', nargs='+', required=True)
ap.add_argument('--pages', type=int, default=8, help='동마다 무작위로 뽑을 페이지(100건/페이지) 수')
ap.add_argument('--max-buildings', type=int, default=150); ap.add_argument('--seed', type=int, default=11)
ap.add_argument('--out', default='output/ledger_stock_p')
a = ap.parse_args()
key = re.findall(r'[A-Za-z0-9%+=/]{40,}', Path(a.key_file).read_text(encoding='utf-8'))[0]
random.seed(a.seed)
S = requests.Session()


def call(op, **kw):
    p = {'serviceKey': unquote(key), 'platGbCd': '0', '_type': 'json'}
    p.update(kw)
    for t in range(3):
        try:
            r = S.get(BASE + op, params=p, timeout=40); r.raise_for_status(); return r.json()['response']['body']
        except Exception:
            time.sleep(1.5)
    return {}


def items(body):
    it = (body.get('items') or {})
    it = it.get('item') if isinstance(it, dict) else None
    return [] if it is None else (it if isinstance(it, list) else [it])


def to_i(x):
    try: return int(float(x))
    except (TypeError, ValueError): return None


# 1) 동별 무작위 페이지 표본 -> 다가구 주건축물만
blds = []
for d in a.dongs:
    b0 = call('getBrTitleInfo', sigunguCd=a.gu, bjdongCd=d, numOfRows=100, pageNo=1)
    total = to_i(b0.get('totalCount')) or 0
    npages = max(1, -(-total // 100))
    pages = random.sample(range(1, npages + 1), min(a.pages, npages))
    seen = 0
    for pg in pages:
        for it in items(call('getBrTitleInfo', sigunguCd=a.gu, bjdongCd=d, numOfRows=100, pageNo=pg)):
            seen += 1
            blds.append(dict(it, dong_cd=d))
        time.sleep(0.1)
    print(f'동 {d}: 전체 {total}건 중 무작위 {seen}건 조회', flush=True)
T = pd.DataFrame(blds)
for c in ('mainAtchGbCd', 'mainPurpsCdNm', 'etcPurps', 'grndFlrCnt', 'ugrndFlrCnt', 'hhldCnt', 'fmlyCnt'):
    if c not in T.columns: T[c] = None
main = T[T['mainAtchGbCd'].astype(str) == '0'].copy()
print('주건축물:', len(main), '| 주용도 상위:', main['mainPurpsCdNm'].value_counts().head(6).to_dict())
dag = main[main['etcPurps'].astype(str).str.contains('다가구') | (main['mainPurpsCdNm'].astype(str).str.contains('다가구'))].copy()
print('다가구주택 건물:', len(dag), '| etcPurps 예:', main['etcPurps'].astype(str).value_counts().head(5).to_dict())
dag['ug'] = dag['ugrndFlrCnt'].map(to_i); dag['gr'] = dag['grndFlrCnt'].map(to_i)
dag = dag.dropna(subset=['ug'])
res = {'다가구 건물(표본)': len(dag), '지하층 있는 건물 비율(%)': round(100 * (dag['ug'] > 0).mean(), 1) if len(dag) else None,
       '지하층수 평균': round(float(dag['ug'].mean()), 2) if len(dag) else None}
print(res)
dag.to_csv(a.out + '_buildings.csv', index=False, encoding='utf-8-sig')

# 2) 층별개요: 지하층의 주거 용도 면적 비율 (지하층이 있는 건물 + 없는 건물 일부를 함께 봐서 전체 비율 계산)
sample = dag.sample(min(a.max_buildings, len(dag)), random_state=a.seed) if len(dag) else dag
HOUSING = re.compile(r'단독주택|다가구|주택|공동주택|다세대|연립|원룸|도시형')
NONH = re.compile(r'주차|창고|기계|전기|보일러|물탱크|계단|공용|저수조|방공|대피|근린|사무|점포|소매|휴게|일반음식|제1종|제2종')
rows = []
for i, b in enumerate(sample.itertuples(), 1):
    fl = items(call('getBrFlrOulnInfo', sigunguCd=a.gu, bjdongCd=b.dong_cd, bun=str(b.bun).zfill(4), ji=str(b.ji).zfill(4), numOfRows=200, pageNo=1))
    fl = [f for f in fl if str(f.get('mgmBldrgstPk')) == str(b.mgmBldrgstPk)]
    base_area = up_area = 0.0; nb_floors = 0
    for f in fl:
        area = float(f.get('area') or 0)
        purp = f"{f.get('mainPurpsCdNm') or ''} {f.get('etcPurps') or ''}"
        is_h = bool(HOUSING.search(purp)) and not NONH.search(purp)
        gb = str(f.get('flrGbCdNm') or '')
        if not is_h:
            continue
        if '지하' in gb: base_area += area; nb_floors += 1
        else: up_area += area
    rows.append(dict(pk=b.mgmBldrgstPk, ug=b.ug, gr=b.gr, base_h_area=base_area, up_h_area=up_area, base_h_floors=nb_floors,
                     hh=to_i(b.hhldCnt), fm=to_i(b.fmlyCnt), n_floor_rows=len(fl)))
    if i % 25 == 0: print(f'  층별개요 {i}/{len(sample)}', flush=True)
    time.sleep(0.1)
F = pd.DataFrame(rows)
F.to_csv(a.out + '_floors.csv', index=False, encoding='utf-8-sig')
ok = F[F['n_floor_rows'] > 0]
tot_base, tot_up = ok['base_h_area'].sum(), ok['up_h_area'].sum()
res2 = {'층별개요 조회 성공 건물': len(ok), '지하층에 주거 용도가 있는 건물 비율(%)': round(100 * (ok['base_h_area'] > 0).mean(), 1) if len(ok) else None,
        '지하 주거면적 ÷ 전체 주거면적(%) [면적 가중, 전체 건물]': round(100 * tot_base / max(tot_base + tot_up, 1e-9), 1),
        '건물별 지하 주거면적 비율 중앙값(%)': round(100 * float((ok['base_h_area'] / (ok['base_h_area'] + ok['up_h_area']).replace(0, float('nan'))).median()), 1) if len(ok) else None}
print(res2)
pd.Series({**res, **res2}).to_csv(a.out + '_summary.csv', header=['값'], encoding='utf-8-sig')
