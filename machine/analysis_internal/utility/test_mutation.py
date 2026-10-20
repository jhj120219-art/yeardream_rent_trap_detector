# -*- coding: utf-8 -*-
"""변이 시험: 안전장치를 일부러 망가뜨린 estimate 를 만들어 test_safety_combos 가 위반을 잡아내는지 확인한다(시험의 탐지 능력 점검).
잡아내지 못하는 변이가 있으면 그 규칙은 시험으로 보호되지 않는다는 뜻이다.
사용: python test_mutation.py (utility 폴더에서, 약 4분)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'demo'))
import app
import test_safety_combos as T

orig_decompose = app.decompose


def m_no_metering_check(M, items, included, itemized, metering):       # 계량 방식 확인 생략
    return orig_decompose(M, items, included, itemized, '세대별')


def m_ignore_total(M, items, included, itemized, metering):            # 총액이 없어도 가상 값을 넣음
    return orig_decompose(M if M is not None else 100000, items, included, itemized, metering)


def m_actual_always(M, items, included, itemized, metering):           # 금액 미표기 항목도 표기된 것처럼 취급
    return orig_decompose(M, items, included, {k: 1 for k in included}, '세대별')


def run(name, fn):
    app.decompose = fn
    n, bad = T.main(quick=True, est=app.estimate)
    app.decompose = orig_decompose
    kinds = sorted({b[0] for b in bad})
    print(f'변이 {name}: 위반 {len(bad)}건 감지 → {"잡힘" if bad else "못 잡음(!)"} {kinds}')
    return bool(bad)


if __name__ == '__main__':
    base_n, base_bad = T.main(quick=True, est=app.estimate)
    print(f'원본: 조합 {base_n} 위반 {len(base_bad)}')
    ok = [run('계량방식 확인 생략', m_no_metering_check), run('총액 없이 구성 표시', m_ignore_total), run('미표기 항목을 금액 표기로 취급', m_actual_always)]
    sys.exit(0 if (not base_bad and all(ok)) else 1)
