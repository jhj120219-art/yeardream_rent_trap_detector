# -*- coding: utf-8 -*-
"""관리비 계산에 필요한 데이터 파일 위치와, 없을 때 알려 주는 메시지.

energy_reference_2023.csv (가구에너지패널 14차(2023) 결과표를 옮긴 표)
  - 저장소에는 올라가지 않는다(재배포 조건 확인 전). 같은 파일을 받거나 아래 방법으로 직접 만든다.
  - 찾는 순서: 환경변수 ENERGY_REFERENCE_CSV -> machine/data/utility_stats/energy_reference_2023.csv -> utility/reference_data/energy_reference_2023.csv
  - 서울 가구 표('3_' 표)만 쓰므로 서울만 담은 작은 파일(약 1,000행)도 그대로 동작한다.
"""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
MACHINE = HERE.parents[1]
ENV_ENERGY = 'ENERGY_REFERENCE_CSV'

HOW_TO_ENERGY = """\
[energy_reference_2023.csv 준비 방법]
 A) 이미 가진 사람에게 파일을 받아 아래 중 한 곳에 둔다.
      machine/data/utility_stats/energy_reference_2023.csv   (또는)   machine/analysis_internal/utility/reference_data/energy_reference_2023.csv
    다른 위치에 두려면 환경변수로 알려 준다:  ENERGY_REFERENCE_CSV=<파일 경로>   (도커/서버에서는 이 방법이 편하다)
 B) 직접 만들기
    1. 국가에너지통계종합정보시스템(KESIS) > 데이터 다운로드 > 결과표 에서 '가구에너지패널조사 14차(2023년 기준) 결과표'를 받는다(자료사용목적 등록 필요).
    2. 압축을 풀어 엑셀 4개를 machine/data/utility_stats/keei/hep14/ 에 둔다.
    3. python analysis_internal/utility/parse_hep14.py   (openpyxl 필요) -> machine/data/utility_stats/energy_reference_2023.csv 생성
"""


class MissingDataFile(FileNotFoundError):
    """필요한 데이터 파일이 없을 때: 어떤 파일이고 어디에 두며 어떻게 만드는지를 메시지에 담는다."""


def energy_reference_csv() -> Path:
    """사용할 energy_reference_2023.csv 경로(존재 여부와 상관없이 가장 먼저 후보가 되는 경로 또는 이미 있는 경로)."""
    cands = []
    if os.environ.get(ENV_ENERGY):
        cands.append(Path(os.environ[ENV_ENERGY]))
    cands += [MACHINE / 'data' / 'utility_stats' / 'energy_reference_2023.csv', HERE / 'reference_data' / 'energy_reference_2023.csv']
    for c in cands:
        if c.exists():
            return c
    return cands[0]


def require_energy_reference() -> Path:
    p = energy_reference_csv()
    if not p.exists():
        raise MissingDataFile(f'필요한 파일이 없습니다: {p}\n' + HOW_TO_ENERGY)
    return p
