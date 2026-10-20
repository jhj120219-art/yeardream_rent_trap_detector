# -*- coding: utf-8 -*-
"""상세보기 파서 시험. real/detail_modals_dev.jsonl(개발용 14건, 로컬)에 대해 사람이 붙인 정답과 비교. 개발 데이터이므로 독립 평가 아님.
사용: python test_parse_detail.py"""
import json
import sys
from pathlib import Path

from parse_detail import parse_detail

HERE = Path(__file__).resolve().parent
# idx: (총액, 정액/실비, 포함 공과금, 별도 실비 공과금, 항목금액 키)
EXP = {
    0: (6000, ['수도'], [], []), 1: (90000, [], [], []), 2: (449000, ['수도', '전기', '가스', '인터넷'], [], ['공용', '사용료', '전기', '수도', '가스', '난방', '인터넷', 'TV']),
    3: (80000, ['수도', '인터넷'], [], []), 4: (70000, ['수도', '인터넷'], [], []), 5: (100000, [], ['수도', '전기', '가스', '인터넷'], ['공용']),
    6: (50000, ['수도', '인터넷'], [], []), 7: (50000, [], [], []), 8: (100000, ['수도', '인터넷'], [], []), 9: (10000, [], [], []),
    10: (10000, [], [], []), 11: (110000, ['수도', '인터넷'], [], []), 12: (10000, [], [], []), 13: (70000, ['인터넷'], [], []),
}


def main():
    bad = 0
    for l in (HERE / 'real' / 'detail_modals_dev.jsonl').read_text(encoding='utf-8').splitlines():
        d = json.loads(l)
        if d['idx'] not in EXP or not d.get('modal'):
            continue
        tot, inc, sep, amt = EXP[d['idx']]
        r = parse_detail(d['modal'])
        ok = r['total'] == tot and r['utility_included'] == inc and r['utility_separate'] == sep and sorted(r['amounts']) == sorted(amt)
        bad += not ok
        print(('OK ' if ok else 'BAD'), d['idx'], r['total'], r['mode'], '포함', r['utility_included'], '별도', r['utility_separate'], '금액', r['amounts'], '' if ok else f'기대 {EXP[d["idx"]]}')
    print('불일치', bad, '/ 14 (개발 데이터)')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
