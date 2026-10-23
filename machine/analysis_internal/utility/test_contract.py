# -*- coding: utf-8 -*-
"""골든 파일 계약 시험: contract_tests/inputs/*.json 을 run_maintenance 에 넣어 '안정 보기'가 contract_tests/expected/*.json 과 같은지 확인한다.
백엔드가 보내는 JSON(FIVE_ITEMS_V1)이 머신에서 어떤 결과로 바뀌는지 고정해 두는 시험이다. 입력 파일의 "_test_hint" 는 시험 환경 지정용(요청 본문 아님).
  c01 정상 5항목 / c02 포함·별도 혼합(이중 합산 방지) / c03 인터넷 이용 가능 / c04 무료(0)와 미확인(null) / c05 기타만 / c06 모순 입력
  c07 데이터 파일 누락 / c08 지원하지 않는 계약 버전
실행: python -X utf8 -m utility.test_contract [--update]   (analysis_internal 에서. --update 는 기대값을 새로 쓴다: 결과를 눈으로 확인한 뒤에만 사용)"""
import json
import os
import sys
import tempfile
from pathlib import Path

from . import data_files as D
from . import reference as R
from .integration import run_maintenance

HERE = Path(__file__).resolve().parent / 'contract_tests'
UPDATE = '--update' in sys.argv


def stable_view(r):
    """시각·경로처럼 바뀌는 값은 빼고, 계약상 의미 있는 값만 모은 보기."""
    est = [dict(t=u['utility_type'], inc=u['inclusion'], st=u['estimate_status'], ad=u['advertised_amount_krw'], lo=u['reference_low_krw'], hi=u['reference_high_krw'])
           for u in r.get('utility_estimates', [])]
    other = (r.get('items') or {}).get('OTHER') or {}
    return dict(
        schema_version=r['schema_version'], source_contract_version=r.get('source_contract_version'), status=r['status'], status_reason=r['status_reason'],
        errors=[e['code'] for e in r.get('errors', [])], reason_codes=r['reason_codes'], missing_fields=r['missing_fields'],
        decomposition=dict(enabled=r['decomposition']['enabled'], status=r['decomposition']['status']),
        other=dict(amount=other.get('advertised_amount_krw'), source=other.get('amount_source'), descriptions=other.get('descriptions')),
        internet_availability=(r.get('items') or {}).get('internet_availability'),
        advertised_total=(r.get('advertised') or {}).get('maintenance_total_krw'),
        utility_estimates=est, separate_items=[s['utility_type'] for s in r.get('separate_items', [])],
        reference_comparison=[c['utility_type'] for c in r.get('reference_comparison', [])],
        input_warnings=[w['code'] for w in r.get('input_warnings', [])])


def run_case(payload):
    hint = payload.pop('_test_hint', None)
    if hint != 'no_energy_file':
        return run_maintenance(payload)
    saved = (D.MACHINE, D.HERE, R._cache, os.environ.pop(D.ENV_ENERGY, None))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            D.MACHINE = D.HERE = Path(tmp) / 'none'
            R._cache = None
            return run_maintenance(payload)
    finally:
        D.MACHINE, D.HERE, R._cache = saved[0], saved[1], None
        if saved[3]:
            os.environ[D.ENV_ENERGY] = saved[3]


def main():
    try:
        D.require_energy_reference()
    except D.MissingDataFile as e:
        print('이 시험에는 energy_reference_2023.csv 가 필요합니다.\n' + str(e))
        return 2
    (HERE / 'expected').mkdir(exist_ok=True)
    fails = 0
    for f in sorted((HERE / 'inputs').glob('c*.json')):
        payload = json.loads(f.read_text(encoding='utf-8'))
        view = stable_view(run_case(payload))
        exp_file = HERE / 'expected' / f.name
        if UPDATE:
            exp_file.write_text(json.dumps(view, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
            print('WROTE', f.name)
            continue
        if not exp_file.exists():
            print('FAIL', f.name, '기대값 파일이 없음 (--update 로 만들고 내용을 확인하세요)')
            fails += 1
            continue
        exp = json.loads(exp_file.read_text(encoding='utf-8'))
        ok = json.dumps(view, ensure_ascii=False, sort_keys=True) == json.dumps(exp, ensure_ascii=False, sort_keys=True)
        print(('PASS ' if ok else 'FAIL ') + f.name)
        if not ok:
            fails += 1
            for k in sorted(set(view) | set(exp)):
                if view.get(k) != exp.get(k):
                    print(f'    {k}: 기대 {exp.get(k)!r}\n    {" " * len(k)}  실제 {view.get(k)!r}')
    print('\n실패', fails, '건')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
