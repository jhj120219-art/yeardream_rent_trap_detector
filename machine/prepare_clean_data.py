# -*- coding: utf-8 -*-
"""수집한 서울시 전월세 원본(data/rent_*.csv)을 정제해 output/clean_rent_data.csv 를 만든다(월세 비교 엔진의 비교 풀).
output 폴더가 없으면 만들고, 입력 파일이 없으면 어떤 파일이 필요한지 알려 준다.
사용:  python prepare_clean_data.py [--raw "data/rent_*_2025_2026.csv"] [--out output/clean_rent_data.csv]
원본 수집: python collect_rent.py --key-file KEY.txt --years 2025 2026 --gu 11620 --out data/rent_gwanak_2025_2026.csv  (구 코드마다 반복)
"""
import argparse
import glob
import sys
from pathlib import Path

import pandas as pd

import compare_rent as cr

HERE = Path(__file__).resolve().parent


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default=str(HERE / 'data' / 'rent_*_2025_2026.csv'), help='원본 CSV 경로 패턴(구별 파일)')
    ap.add_argument('--out', default=str(HERE / 'output' / 'clean_rent_data.csv'))
    a = ap.parse_args(argv)
    files = sorted(glob.glob(a.raw))
    if not files:
        print(f'필요한 파일이 없습니다: {a.raw}\n'
              '서울시 전월세 원본이 필요합니다. 수집: python collect_rent.py --key-file KEY.txt --years 2025 2026 --gu <구 코드> --out data/rent_<구>_2025_2026.csv\n'
              '(서울 열린데이터광장 인증키 필요. 자세한 내용은 docs/data_and_licenses.md)', file=sys.stderr)
        return 2
    parts, reports = [], []
    for f in files:
        raw = pd.read_csv(f, dtype=str)
        rent, rep = cr.clean(raw)
        parts.append(rent)
        reports.append({'파일': Path(f).name, **rep})
        print(f'{Path(f).name}: 원본 {len(raw):,}건 -> 정제 {len(rent):,}건')
    rent = pd.concat(parts, ignore_index=True)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)               # 결과 폴더가 없으면 만든다
    rent.drop(columns=[c for c in rent.columns if c in ('LOTNO_SE', 'LOTNO_SE_NM')]).to_csv(out, index=False, encoding='utf-8-sig')
    print(f'저장: {out}  ({len(rent):,}건, {rent["gu"].nunique()}개 구)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
