# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from parse_ad_text import parse_ad
from heldout_cases import CASES
tot = {'deposit': 0, 'rent': 0, 'maint': 0, 'state': 0, 'included': 0, 'excluded': 0}
for i, (text, dep, rent, maint, state, inc, exc) in enumerate(CASES, 1):
    r = parse_ad(text)
    ok = {'deposit': r['deposit_10k_krw'] == dep, 'rent': r['rent_10k_krw'] == rent,
          'maint': (r['maintenance_10k_krw'] is None and maint is None) or (r['maintenance_10k_krw'] is not None and maint is not None and abs(r['maintenance_10k_krw'] - maint) < 0.01),
          'state': r['maintenance_state'] == state, 'included': sorted(r['maintenance_included_items']) == sorted(inc), 'excluded': sorted(r['maintenance_excluded_items']) == sorted(exc)}
    for k, v in ok.items():
        tot[k] += int(v)
    if not all(ok.values()):
        print(f'#{i} 불일치 {[k for k, v in ok.items() if not v]} | 파서: 보증금 {r["deposit_10k_krw"]} 월세 {r["rent_10k_krw"]} 관리비 {r["maintenance_10k_krw"]}({r["maintenance_state"]}) 포함 {r["maintenance_included_items"]} 별도 {r["maintenance_excluded_items"]} | 정답: {dep}/{rent}/{maint}/{inc}/{exc}')
        print('    원문:', text.replace('\n', ' | '))
print('필드별:', {k: f'{v}/{len(CASES)}' for k, v in tot.items()})
print('전부 일치:', sum(1 for c in CASES if True) and '위 불일치 목록 외 모두 일치')
