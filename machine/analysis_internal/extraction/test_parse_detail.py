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


ZB_CASE = ('관리비 : 70,000원 일반(공용) 관리비 70,000원 사용료 전기 실비 수도 실비 가스 실비 난방 실비 인터넷 실비 TV 실비 기타 관리비 해당 없음 최근 3개월 관리비 평균',
           70000, [], ['수도', '전기', '가스', '인터넷'], ['공용'])


def main():
    bad = 0
    dev = HERE / 'real' / 'detail_modals_dev.jsonl'   # 실제 광고 캡처에서 읽은 개발용 14건: 저장소에 없고 로컬에만 있음
    if not dev.exists():
        print('개발용 캡처 14건 없음 — 직방 1건만 확인')
    for l in (dev.read_text(encoding='utf-8').splitlines() if dev.exists() else []):
        d = json.loads(l)
        if d['idx'] not in EXP or not d.get('modal'):
            continue
        tot, inc, sep, amt = EXP[d['idx']]
        r = parse_detail(d['modal'])
        ok = r['total'] == tot and r['utility_included'] == inc and r['utility_separate'] == sep and sorted(r['amounts']) == sorted(amt)
        bad += not ok
        print(('OK ' if ok else 'BAD'), d['idx'], r['total'], r['mode'], '포함', r['utility_included'], '별도', r['utility_separate'], '금액', r['amounts'], '' if ok else f'기대 {EXP[d["idx"]]}')
    t, tot, inc, sep, amt = ZB_CASE                      # 직방 상세 표기 1건(개발용, 개인정보 제외한 관리비 부분만)
    r = parse_detail(t)
    ok = r['total'] == tot and r['utility_included'] == inc and r['utility_separate'] == sep and sorted(r['amounts']) == sorted(amt)
    bad += not ok
    print(('OK ' if ok else 'BAD'), '직방', r['total'], r['mode'], '포함', r['utility_included'], '별도', r['utility_separate'], '금액', r['amounts'])
    print('불일치', bad, '/ 14 (개발 데이터)')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
