# -*- coding: utf-8 -*-
"""분석 내부 공통: 데이터 로드, 기준 매물 선정, 해시·버전 기록. 팀원 형식(analyze.py, 계약 v1.1)과 무관."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTERNAL = Path(__file__).resolve().parent
for p in (ROOT, ROOT / '_libs'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import numpy as np
import pandas as pd

DTYPES = {'MNO': str, 'SNO': str, 'STDG_CD': str, 'CGG_CD': str}


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def code_version() -> str:
    try:
        head = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--', 'analysis_internal', 'compare_rent.py'],
                               capture_output=True, text=True).stdout.strip()
        return head + ('+local' if dirty else '')
    except Exception:
        return 'unknown'


def load_policy(path=None) -> dict:
    path = Path(path or INTERNAL / 'configs' / 'candidate_v2.json')
    return json.loads(path.read_text(encoding='utf-8'))


def load_rent(csv_path) -> pd.DataFrame:
    rent = pd.read_csv(csv_path, parse_dates=['date'], low_memory=False, dtype=DTYPES)
    for c in ('is_new', 'basement', 'dup_suspect'):
        rent[c] = rent[c].astype(bool)
    return rent


def load_building_cache(csv_path) -> dict:
    """(CGG_CD, STDG_CD, MNO, SNO) -> 주건축물 수. 조회 성공(ok=True) 지번만. 실패 지번은 포함하지 않는다."""
    c = pd.read_csv(csv_path, dtype=str)
    c = c[c['ok'] == 'True']
    return {(a, b, m, s): int(n) for a, b, m, s, n in zip(c.CGG_CD, c.STDG_CD, c.MNO, c.SNO, c.n_main)}


def make_bases(rent: pd.DataFrame, seed: int, per_gu: int, recent_months: int) -> pd.DataFrame:
    """설계 백테스트 기준 매물: 구별 최근 N개월 신규 계약에서 무작위 per_gu건. (run_validation.py 와 동일 방식·시드)"""
    new = rent[rent['is_new']]
    parts = []
    for _, g in new.groupby('gu'):
        g = g[g['date'] >= g['date'].max() - pd.DateOffset(months=recent_months)]
        parts.append(g.sample(min(per_gu, len(g)), random_state=seed))
    return pd.concat(parts).reset_index(drop=True)
