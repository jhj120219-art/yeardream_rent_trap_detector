# reference_data

`energy_reference_2023.csv`: 가구에너지패널 14차(2023) 공개 결과표(KESIS/KEEI)에서 서울 가구 표만 옮긴 집계표(약 1,000행, 마이크로데이터 아님). 관리비 참고 범위(전기·가스) 계산에 필요합니다.
이 파일은 `machine/data/utility_stats/`나 환경변수 `ENERGY_REFERENCE_CSV`로 다른 파일을 지정하면 그쪽이 우선합니다. 다시 만들려면 `python analysis_internal/utility/parse_hep14.py`.
