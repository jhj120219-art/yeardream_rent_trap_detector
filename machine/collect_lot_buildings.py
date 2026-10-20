#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""지번별 주건축물 수 캐시 — 건축HUB 표제부(getBrTitleInfo). 설계 데이터에서 신규 거래 3건 이상인 아파트·연립다세대·오피스텔 지번.
재시작 가능(이미 받은 지번은 건너뜀). 조회 실패는 ok=False 로 기록하며 '1동'으로 간주하지 않는다. 키는 출력하지 않는다.
사용: python collect_lot_buildings.py --key-file KEY.txt [--limit 9000] [--min-trades 3]
출력: data/lot_buildings_cache.csv (CGG_CD, STDG_CD, MNO, SNO, ok, n_total, n_main, purposes, fetched_at)
"""
import argparse, csv, re, time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
import pandas as pd
import requests

HERE = Path(__file__).parent
BASE = 'http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo'
ap = argparse.ArgumentParser()
ap.add_argument('--key-file', required=True)
ap.add_argument('--limit', type=int, default=9000)
ap.add_argument('--min-trades', type=int, default=3)
ap.add_argument('--lots-file', default=None, help='조회할 지번 목록 CSV(CGG_CD,STDG_CD,MNO,SNO). 지정하면 거래 건수 조건 없이 이 목록만 조회')
ap.add_argument('--cache-out', default=None)
a = ap.parse_args()
key = re.findall(r'[A-Za-z0-9%+=/]{40,}', Path(a.key_file).read_text(encoding='utf-8'))[0]

r = pd.read_csv(HERE / 'output' / 'clean_rent_data.csv', usecols=['CGG_CD', 'STDG_CD', 'MNO', 'SNO', 'usage', 'is_new'], dtype=str)
r = r[(r.usage != '단독다가구') & r.MNO.notna() & r.SNO.notna() & (r.is_new == 'True')]
cnt = r.groupby(['CGG_CD', 'STDG_CD', 'MNO', 'SNO']).size().reset_index(name='n')
cnt = cnt[cnt.n >= a.min_trades].sort_values('n', ascending=False)
if a.lots_file:
    cnt = pd.read_csv(a.lots_file, dtype=str)
cache =Path(a.cache_out) if a.cache_out else HERE / 'data' / 'lot_buildings_cache.csv'
done = set()
if cache.exists():
    d = pd.read_csv(cache, dtype=str)
    done = set(zip(d.CGG_CD, d.STDG_CD, d.MNO, d.SNO))
    # 이전 실험(400곳) 결과는 별도 파일이라 재조회 대상. 실패 기록은 재시도
    done = set(zip(d[d.ok == 'True'].CGG_CD, d[d.ok == 'True'].STDG_CD, d[d.ok == 'True'].MNO, d[d.ok == 'True'].SNO))
todo = [t for t in zip(cnt.CGG_CD, cnt.STDG_CD, cnt.MNO, cnt.SNO) if t not in done][:a.limit]
print('대상', len(cnt), '지번 / 이미 완료', len(done), '/ 이번 조회', len(todo), flush=True)
new_file = not cache.exists()
f = open(cache, 'a', newline='', encoding='utf-8-sig')
w = csv.writer(f)
if new_file:
    w.writerow(['CGG_CD', 'STDG_CD', 'MNO', 'SNO', 'ok', 'n_total', 'n_main', 'purposes', 'fetched_at'])
S = requests.Session()
fails = 0
for n, (cgg, stdg, mno, sno) in enumerate(todo):
    params = {'serviceKey': unquote(key), 'sigunguCd': cgg, 'bjdongCd': stdg, 'platGbCd': '0',
              'bun': str(mno).zfill(4), 'ji': str(sno).zfill(4), 'numOfRows': 100, 'pageNo': 1, '_type': 'json'}
    items = None
    for t in range(3):
        try:
            resp = S.get(BASE, params=params, timeout=40)
            j = resp.json()['response']['body']
            it = j.get('items') or {}
            it = it.get('item') if isinstance(it, dict) else None
            items = [] if it is None else (it if isinstance(it, list) else [it])
            break
        except Exception:
            time.sleep(1.5)
    now = datetime.now().isoformat(timespec='seconds')
    if items is None:
        fails += 1
        w.writerow([cgg, stdg, mno, sno, False, '', '', '', now])
        if fails >= 30 and fails > n * 0.2:
            print('실패가 많아 중단(한도 초과 또는 서비스 오류 가능)', n, fails, flush=True)
            break
    else:
        main = [x for x in items if str(x.get('mainAtchGbCd')) == '0']
        w.writerow([cgg, stdg, mno, sno, True, len(items), len(main), '/'.join(sorted({str(x.get('mainPurpsCdNm')) for x in main})), now])
    if n % 200 == 0:
        f.flush()
        print(n, '/', len(todo), '실패', fails, flush=True)
    time.sleep(0.1)
f.close()
print('끝. 실패', fails, flush=True)
