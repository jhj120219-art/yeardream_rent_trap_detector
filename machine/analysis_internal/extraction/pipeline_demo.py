# -*- coding: utf-8 -*-
"""전사 텍스트 -> 규칙 파서 -> 관리비 점검(utility.check). 합성 광고 결과(hybrid_results.json)를 이어 붙여 보여주는 데모."""
import json
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from utility.check import assess

MAP = {'수도': 'water', '전기': 'electric', '가스': 'gas', '인터넷': 'internet'}
UNMODELED = {'청소', '공용전기', '승강기', '난방', '공과금', 'TV', '케이블'}


def run(parsed, month=10, household=1):
    inc = [MAP[x] for x in parsed['maintenance_included_items'] if x in MAP]
    out = assess(month=month, household=household, included=inc, mgmt_total=(parsed['maintenance_10k_krw'] or 0) * 10000 or None)
    out['unmodeled_included'] = [x for x in parsed['maintenance_included_items'] if x in UNMODELED]
    out['excluded_by_ad'] = parsed['maintenance_excluded_items']
    out['maintenance_state'] = parsed['maintenance_state']
    return out


if __name__ == '__main__':
    res = json.loads((HERE / 'synthetic' / 'hybrid_results.json').read_text(encoding='utf-8'))
    for name in ('ad_01', 'ad_03', 'ad_08'):
        p = res[name]['parsed']
        o = run(p)
        print(f"== {name}: 관리비 {p['maintenance_10k_krw']}만원, 포함 {p['maintenance_included_items']}, 별도 {p['maintenance_excluded_items']}")
        print('   상태:', o['status'], '| 참고 범위:', {v['name']: (v.get('reference_low'), v.get('reference_high')) for v in o['items'].values()}, '| 모델에 없는 포함 항목:', o['unmodeled_included'])
