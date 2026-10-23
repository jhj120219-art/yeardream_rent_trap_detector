#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""가구에너지패널조사 14차(2023년 기준) 결과표 엑셀 -> 정리된 CSV (서울·전국 블록 포함).
입력: machine/data/utility_stats/keei/hep14/*.xlsx (국가에너지통계종합정보시스템 결과표, 사용 목적 등록 후 다운로드)
출력: data/utility_stats/energy_reference_2023.csv  (table, sheet, region, category, item, unit, estimate, rse_pct)
결과표의 값을 그대로 옮길 뿐 합치거나 추정하지 않는다. 표마다 조건이 다르므로 서로 다른 표를 곱해 조건부 평균으로 쓰지 말 것.
"""
import re
import sys
from pathlib import Path
import csv
import glob
try:
    import openpyxl
except ImportError:
    sys.exit('openpyxl 이 필요합니다:  pip install openpyxl')

HERE = Path(__file__).resolve().parents[2]   # machine/
rows_out = []
SRC = HERE / 'data' / 'utility_stats' / 'keei' / 'hep14'
files = sorted(glob.glob(str(SRC / '*.xlsx')))
if not files:
    sys.exit(f'필요한 파일이 없습니다: {SRC}\\*.xlsx\n'
             'KESIS(국가에너지통계종합정보시스템) > 데이터 다운로드 > 결과표 에서 "가구에너지패널조사 14차(2023년 기준) 결과표"를 받아(자료사용목적 등록 필요) '
             '엑셀 4개를 위 폴더에 두세요. 완성된 energy_reference_2023.csv 를 이미 받았다면 이 단계는 필요 없습니다.')
for f in files:
    tname = re.search(r'결과표_(\d_[^_]+)', Path(f).name).group(1)
    wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
    for ws in wb.worksheets:
        region, cats, mode = None, None, None
        for r in ws.iter_rows(values_only=True):
            v = [x for x in r if x not in (None, '')]
            if not v:
                continue
            first = str(v[0]).strip()
            m = re.match(r'^\d{1,2}\)\s*(.+)$', first)
            if m and len(v) == 1:
                region, cats = m.group(1).strip(), None
                continue
            if len(v) == 2 and '추정값' in str(v[0]) and 'RSE' in str(v[1]):
                cats = None
                mode = 'next_header'
                continue
            if mode == 'next_header':
                n = len(v) // 2
                if len(v) % 2 == 0 and all(isinstance(x, str) for x in v) and [str(x) for x in v[:n]] == [str(x) for x in v[n:]]:
                    cats = [str(x).strip() for x in v[:n]]
                    mode = 'data'
                    continue
            if cats and mode == 'data' and len(v) == 2 * (len(cats) + 2):
                n = len(cats)
                item, unit = str(v[0]).strip(), str(v[1]).strip()
                est, rse = v[2:2 + n], v[2 + n + 2:]
                for c, e, s in zip(cats, est, rse):
                    def num(x):
                        try:
                            return float(x)
                        except (TypeError, ValueError):
                            return ''
                    rows_out.append([tname, ws.title.strip(), region or '', c, item, unit, num(e), num(s)])
out = HERE / 'data' / 'utility_stats' / 'energy_reference_2023.csv'
out.parent.mkdir(parents=True, exist_ok=True)      # 결과 폴더가 없으면 만든다
with open(out, 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.writer(fh)
    w.writerow(['table', 'sheet', 'region', 'category', 'item', 'unit', 'estimate', 'rse_pct'])
    w.writerows(rows_out)
print(len(rows_out), 'rows ->', out)
