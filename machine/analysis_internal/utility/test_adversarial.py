# -*- coding: utf-8 -*-
"""적대적 입력 시험: 모순·이상값을 넣어 estimate() 가 죽지 않고(예외 없음) 근거 없는 구성을 만들지 않는지 본다.
사용: python test_adversarial.py (utility 폴더에서)"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'demo'))
from app import estimate

B = dict(month=10, household=1, mgmt_man=8, included=['수도', '인터넷'], excluded=[], itemized={}, metering='세대별')
CASES = [
    ('포함과 별도에 같은 항목', dict(excluded=['수도']), 'hold'),
    ('관리비 음수', dict(mgmt_man=-5), 'none_or_hold'),
    ('관리비 0', dict(mgmt_man=0), 'none_or_hold'),
    ('관리비 단위 혼동(원을 만원칸에)', dict(mgmt_man=80000), 'hold_or_none'),
    ('항목 금액 합이 총액 초과', dict(itemized={'수도': 90000, '인터넷': 90000}), 'hold'),
    ('항목 금액 0원', dict(itemized={'수도': 0, '인터넷': 0}), 'no_crash'),
    ('빈 문자열 관리비', dict(mgmt_man=''), 'none'),
    ('월 범위 밖', dict(month=13), 'no_crash'),
    ('가구원 0·99', dict(household=0), 'no_crash'),
    ('알 수 없는 항목명', dict(included=['수도', '쓰레기']), 'no_crash'),
    ('포함 항목 전부 + 가스 사용 모름', dict(included=['수도', '전기', '가스', '인터넷']), 'hold'),
]


def main():
    bad = []
    for name, over, want in CASES:
        p = dict(B); p.update(over)
        try:
            r = estimate(p)
        except Exception as e:
            if want != 'crash_ok':
                bad.append((name, '예외', repr(e)[:80]))
            print(f"{'OK ' if want == 'crash_ok' else 'BAD'} {name}: 예외 {type(e).__name__}")
            continue
        t = r['decomposition']['type']
        ok = True
        if want == 'none_or_hold' and t not in ('NONE', 'HOLD'): ok = False
        if want == 'hold_or_none' and t not in ('NONE', 'HOLD'): ok = False
        if want == 'hold' and t != 'HOLD': ok = False
        if want == 'none' and t != 'NONE': ok = False
        if t in ('VIRTUAL', 'MIXED', 'ACTUAL') and r['decomposition'].get('R_low', 0) < 0: ok = False
        if not ok:
            bad.append((name, t))
        print(f"{'OK ' if ok else 'BAD'} {name}: 분해={t}")
    print('실패', len(bad))
    for b in bad: print(' ', b)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
