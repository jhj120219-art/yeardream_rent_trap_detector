# -*- coding: utf-8 -*-
"""규칙 파서 검증: 합성 광고의 원문 텍스트(OCR 이전 단계)를 넣어 정답과 비교. 실행: python test_parser.py"""
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from parse_ad_text import parse_ad
import importlib.util
spec = importlib.util.spec_from_file_location('mk', Path(__file__).parent / 'make_synthetic_ads.py')
mk = importlib.util.module_from_spec(spec); spec.loader.exec_module(mk)

bad = 0
for i, (title, price, lines, truth) in enumerate(mk.CASES, 1):
    text = '\n'.join([title, price] + lines)
    r = parse_ad(text)
    ok = {'deposit': r['deposit_10k_krw'] == truth['deposit'], 'rent': r['rent_10k_krw'] == truth['rent'],
          'maint': (r['maintenance_10k_krw'] is None and truth['maint'] is None) or (r['maintenance_10k_krw'] is not None and truth['maint'] is not None and abs(r['maintenance_10k_krw'] - truth['maint']) < 0.01),
          'included': sorted(r['maintenance_included_items']) == sorted(x.replace('청소비', '청소') for x in truth['included']),
          'excluded': sorted(r['maintenance_excluded_items']) == sorted(truth['excluded']) or truth['excluded'] == ['공과금'] and r['maintenance_excluded_items'] in ([], ['공과금']),
          'area': r['area_m2'] == truth['area'], 'basis': r['area_basis'] == truth['area_basis'], 'floor': r['floor'] == truth['floor']}
    if not all(ok.values()):
        bad += 1
        print(f'ad_{i:02d} 불일치', [k for k, v in ok.items() if not v], r, 'truth', truth)
print('파서: 전부 일치' if not bad else f'파서: {bad}건 불일치')
