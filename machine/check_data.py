# -*- coding: utf-8 -*-
"""실행에 필요한 데이터 파일이 있는지 점검하고, 없는 파일은 이름·위치·만드는 방법을 알려 준다. (파일을 만들거나 바꾸지 않는다)
사용:  python check_data.py
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'analysis_internal'))
from utility import data_files as D      # noqa: E402

ROWS = [
    # (설명, 경로 또는 None, 필수 여부, 만드는 방법)
    ('월세 비교 풀 (정제된 서울시 전월세)', HERE / 'output' / 'clean_rent_data.csv', '월세 비교 엔진 · test_analyze · test_normalize',
     'python collect_rent.py ... 로 구별 원본을 받은 뒤 python prepare_clean_data.py (output 폴더는 자동 생성)'),
    ('가구에너지패널 14차 결과표 표 (energy_reference_2023.csv)', D.energy_reference_csv(), '관리비 점검(참고 사용량) · utility 테스트',
     D.HOW_TO_ENERGY),
]
OPTIONAL = [
    ('마이크로데이터 분포표 (micro_dist_seoul.csv)', HERE / 'data' / 'utility_stats' / 'micro_dist_seoul.csv',
     '없어도 동작(공개 결과표 기반 참고값 사용). 이용 범위 확인 전이라 저장소에 올리지 않음'),
]


def main():
    missing = 0
    print('== 필수 파일 ==')
    for name, path, used_by, how in ROWS:
        ok = Path(path).exists()
        print(f'[{"있음" if ok else "없음"}] {name}\n        경로: {path}\n        쓰임: {used_by}')
        if not ok:
            missing += 1
            print('        만드는 방법:\n' + '\n'.join('          ' + ln for ln in how.splitlines()))
    print('\n== 없어도 되는 파일 ==')
    for name, path, note in OPTIONAL:
        print(f'[{"있음" if Path(path).exists() else "없음"}] {name}  ({note})')
    if os.environ.get(D.ENV_ENERGY):
        print(f'\n환경변수 {D.ENV_ENERGY} = {os.environ[D.ENV_ENERGY]}')
    print('\n' + ('모든 필수 파일이 있습니다.' if not missing else f'필수 파일 {missing}개가 없습니다. 위 안내대로 준비하세요.'))
    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main())
