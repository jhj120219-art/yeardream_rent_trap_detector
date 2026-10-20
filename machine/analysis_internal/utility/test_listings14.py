# -*- coding: utf-8 -*-
"""다방 상세보기 창에서 읽은 실제 표기 14건의 '유형'만 옮긴 회귀 테스트(사진·설명·연락처·주소 없음).
확인 대상: 포함 항목과 별도 실비를 구분해 이중 계산하지 않는지, 근거 없이 가상 구성비를 만들지 않는지.
사용: python test_listings14.py  (utility 폴더에서)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'demo'))
from app import estimate

# (번호, 관리비 만원, 포함 항목, 별도 실비 항목, 항목별 금액(원), 허용되는 분해 유형, 부과 방식 분류)
CASES = [
    (0, 0.6, ['수도'], [], {}, {'HOLD'}, '정액<10만(비목만)'),
    (1, 9, [], [], {}, {'NONE'}, '정액<10만(공용만)'),
    (2, 44.9, ['전기', '수도', '가스', '인터넷'], [], {'전기': 50000, '수도': 50000, '가스': 50000, '인터넷': 50000}, {'ACTUAL'}, '정액>=10만(금액 표기)'),
    (3, 8, ['수도', '인터넷'], [], {}, {'HOLD'}, '정액<10만(비목만)'),
    (4, 7, ['수도', '인터넷'], [], {}, {'HOLD'}, '정액<10만(비목만)'),
    (5, 10, [], ['전기', '수도', '가스', '인터넷'], {}, {'NONE'}, '정액>=10만(공용만+실비 별도)'),
    (6, 5, ['수도', '인터넷'], [], {}, {'HOLD'}, '정액<10만(비목만)'),
    (7, 5, [], [], {}, {'NONE'}, '정액<10만(공용만)'),
    (8, 10, ['수도', '인터넷'], [], {}, {'HOLD'}, '정액 세부내역 미고지'),
    (9, 1, [], [], {}, {'NONE'}, '정액<10만(기타만)'),
    (10, 1, [], [], {}, {'NONE'}, '정액<10만(기타만)'),
    (11, 11, ['수도', '인터넷'], [], {}, {'HOLD'}, '정액 세부내역 미고지'),
    (12, 1, [], [], {}, {'NONE'}, '정액<10만(기타만)'),
    (13, 7, ['인터넷'], [], {}, {'HOLD'}, '정액<10만(비목만)'),
]


def main():
    bad = 0
    for no, m, inc, sep, itm, ok_types, kind in CASES:
        r = estimate(dict(month=10, household=1, mgmt_man=m, included=inc, excluded=sep, itemized=itm, metering='모름'))
        t = r['decomposition']['type']
        KEY = {'수도': 'water', '전기': 'electric', '가스': 'gas', '인터넷': 'internet'}
        dup = [k for k in sep if KEY[k] in r['items']]              # 별도 실비 항목이 포함 항목으로 이중 계산되면 안 됨
        sep_ok = all(KEY[k] in r['separate'] for k in sep)
        ok = t in ok_types and not dup and sep_ok
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} #{no:2d} {kind:28s} 분해={t:6s} 포함={inc} 별도실비={sep}")
    print('불일치', bad, '/', len(CASES))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
