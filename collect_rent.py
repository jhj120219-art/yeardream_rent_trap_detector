#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서울시 부동산 전월세가 정보(tbLnOpendataRentV) 수집.
연도(RCPT_YR)와 자치구 코드(CGG_CD)로 나눠서 받는다(전체 약 266만 건이라 전량은 오래 걸림).
사용 예:
  python collect_rent.py --key-file "키가 적힌 txt" --years 2025 2026 --gu 11620
인증키는 환경변수 SEOUL_API_KEY 도 가능. 키는 화면/파일에 출력하지 않는다.
"""
import argparse, csv, json, os, re, sys, time, urllib.request
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--key-file')
ap.add_argument('--years', nargs='+', required=True)
ap.add_argument('--gu', nargs='+', required=True, help='자치구 코드(예: 관악구 11620)')
ap.add_argument('--out', default='data/rent_raw.csv')
a = ap.parse_args()
key = os.environ.get('SEOUL_API_KEY')
if not key and a.key_file:
    key = re.findall(r'[A-Za-z0-9]{20,}', Path(a.key_file).read_text(encoding='utf-8'))[0]
if not key:
    sys.exit('인증키가 필요합니다')
SVC = 'tbLnOpendataRentV'


def call(start, end, year, gu):
    url = f'http://openapi.seoul.go.kr:8088/{key}/json/{SVC}/{start}/{end}/{year}/{gu}'
    for attempt in range(3):
        try:
            d = json.loads(urllib.request.urlopen(url, timeout=60).read().decode('utf-8-sig'))
            g = d[SVC]
            return g['list_total_count'], g.get('row') or []
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


rows = []
for gu in a.gu:
    for year in a.years:
        idx, total = 1, None
        while True:
            total_now, batch = call(idx, idx + 999, year, gu)
            total = total_now if total is None else total
            rows.extend(batch)
            if len(batch) < 1000 or idx + 999 >= total:
                break
            idx += 1000
        print(f'{gu} {year}: {total:,}건', flush=True)
out = Path(a.out)
out.parent.mkdir(parents=True, exist_ok=True)
cols = list(rows[0].keys())
with open(out, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)
print('saved', out, f'{len(rows):,}건')
