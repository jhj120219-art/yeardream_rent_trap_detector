# -*- coding: utf-8 -*-
"""안전성 시험: 포함/별도/항목금액/계량 방식/관리비 총액/난방·가스 조합을 모두 만들어 estimate() 결과가 규칙을 어기지 않는지 확인.
규칙: (1) 별도 실비 항목은 관리비 내 참고 합계(items)에 없다 (2) 가상 구성(VIRTUAL/MIXED)은 포함 항목이 있고 계량이 '세대별'일 때만
(3) ACTUAL 은 포함 항목이 모두 금액 표기일 때만 (4) 총액이 없으면 NONE (5) 나머지 금액이 음수가 아니다 (6) 결과 전체에 판정 용어가 없다.
조합 수는 출력에 표시한다. '오류 0건'은 이 조합 범위에서 위반이 관찰되지 않았다는 뜻이다.
사용: python test_safety_combos.py  (utility 폴더에서)"""
import itertools
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'demo'))
from app import estimate

NAMES = ['수도', '전기', '가스', '인터넷']
KEY = {'수도': 'water', '전기': 'electric', '가스': 'gas', '인터넷': 'internet'}
FORBID = ['부당', '눈탱이', '바가지', '과다 청구', '과다청구', '폭리', '사기']


def subsets(xs):
    for r in range(len(xs) + 1):
        yield from (list(c) for c in itertools.combinations(xs, r))


def main(quick=False, est=None):
    est = est or estimate
    n, bad = 0, []
    for inc in subsets(NAMES):
        rest = [x for x in NAMES if x not in inc]
        for sep in subsets(rest):
            for itm_mode in ('none', 'all', 'one'):
                itm = {} if itm_mode == 'none' or not inc else ({x: 15000 for x in inc} if itm_mode == 'all' else {inc[0]: 15000})
                for metering in ('모름', '세대별', '공동'):
                    for mg in ((None, 10) if quick else (None, 0.6, 5, 9.9, 10, 20, 44.9)):
                        for heat, gasu in ((('모름', '모름'),) if quick else (('모름', '모름'), ('개별 도시가스', '예'), ('지역난방', '아니오'))):
                            p = dict(month=10, household=1, mgmt_man=mg, included=inc, excluded=sep, itemized=itm, metering=metering, heating=heat, gas_user=gasu)
                            r = est(p)
                            d = r['decomposition']
                            n += 1
                            tag = (inc, sep, itm_mode, metering, mg, heat)
                            if any(KEY[k] in r['items'] for k in sep):
                                bad.append(('별도 실비가 참고 합계에 포함', tag))
                            if d['type'] in ('VIRTUAL', 'MIXED') and (not inc or metering != '세대별'):
                                bad.append(('근거 없는 가상 구성', tag))
                            if d['type'] == 'ACTUAL' and any(x not in itm for x in inc):
                                bad.append(('금액 미표기 항목을 실제 구성으로 표시', tag))
                            if mg is None and d['type'] != 'NONE':
                                bad.append(('총액 없이 구성 표시', tag))
                            if d['type'] in ('VIRTUAL', 'MIXED', 'ACTUAL') and (d.get('R_low') is None or d['R_low'] < 0):
                                bad.append(('음수/없는 나머지', tag))
                            if any(w in json.dumps(r, ensure_ascii=False) for w in FORBID):
                                bad.append(('판정 용어 포함', tag))
    print(f'조합 {n}개 → 위반 {len(bad)}건')
    seen = {}
    for b in bad:
        seen.setdefault(b[0], b[1])
    for k, v in list(seen.items())[:8]:
        print(' ', k, v)
    return n, bad


if __name__ == '__main__':
    sys.exit(1 if main()[1] else 0)
