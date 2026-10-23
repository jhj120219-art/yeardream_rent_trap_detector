# -*- coding: utf-8 -*-
"""필요한 데이터 파일이 없을 때: 멈추지 않고 어떤 파일이 없는지와 준비 방법을 알려 주는지 시험한다(데이터 파일이 없어도 실행됨).
실행: python -X utf8 -m utility.test_data_files   (analysis_internal 에서)"""
import os
import tempfile
from pathlib import Path

from . import data_files as D
from . import reference as R
from .integration import run_maintenance

FAILS = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + (f'  {detail}' if (detail and not cond) else ''))
    if not cond:
        FAILS.append(name)


AD = dict(total=80000, mode='정액', utility_included=['전기'], included=['전기'], amounts={}, actual_items=[], utility_separate=[], excluded_items=[],
          incomplete=[], undisclosed=False, notes=[])
COND = dict(target_month=10, household_size=1, housing_type='다세대·연립', area_m2=20)

saved = (D.MACHINE, D.HERE, R._cache, os.environ.pop(D.ENV_ENERGY, None))
try:
    with tempfile.TemporaryDirectory() as tmp:
        D.MACHINE = D.HERE = Path(tmp) / 'none'          # energy_reference_2023.csv 가 어디에도 없는 상태를 만든다
        R._cache = None
        p = D.energy_reference_csv()
        check('경로 후보는 항상 돌려준다(없어도)', p.name == 'energy_reference_2023.csv')
        try:
            D.require_energy_reference()
            check('require: 파일이 없으면 MissingDataFile', False)
        except D.MissingDataFile as e:
            msg = str(e)
            check('require: 없는 파일 이름과 경로를 알려 준다', 'energy_reference_2023.csv' in msg and str(p) in msg)
            check('require: 만드는 방법(받아 두기 · 환경변수 · 직접 만들기)을 알려 준다', 'ENERGY_REFERENCE_CSV' in msg and 'parse_hep14.py' in msg and 'KESIS' in msg)
        check('MissingDataFile 은 FileNotFoundError', issubclass(D.MissingDataFile, FileNotFoundError))
        r = run_maintenance(dict(ad=AD, conditions=COND))
        check('run_maintenance: 크래시 없이 errors 에 MISSING_DATA_FILE', bool(r['errors']) and r['errors'][0]['code'] == 'MISSING_DATA_FILE', str(r['errors'])[:200])
        check('run_maintenance: 상태 INSUFFICIENT_DATA + 사유 MISSING_DATA_FILE', r['status'] == 'INSUFFICIENT_DATA' and 'MISSING_DATA_FILE' in r['status_reason'], str(r['status_reason']))
        check('run_maintenance: how_to 에 준비 방법', 'ENERGY_REFERENCE_CSV' in r['errors'][0]['how_to'])
        # 환경변수로 가리키면 그 경로를 쓴다
        f = Path(tmp) / 'ref.csv'
        f.write_text('table,sheet,region,category,item,unit,estimate,rse_pct\n', encoding='utf-8')
        os.environ[D.ENV_ENERGY] = str(f)
        check('환경변수 ENERGY_REFERENCE_CSV 가 있으면 그 파일을 쓴다', D.energy_reference_csv() == f and D.require_energy_reference() == f)
        os.environ.pop(D.ENV_ENERGY, None)
finally:
    D.MACHINE, D.HERE = saved[0], saved[1]
    R._cache = None
    if saved[3]:
        os.environ[D.ENV_ENERGY] = saved[3]

print('\n실패', len(FAILS), '건', FAILS if FAILS else '')
raise SystemExit(1 if FAILS else 0)
