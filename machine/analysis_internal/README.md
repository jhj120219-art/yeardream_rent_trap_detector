# analysis_internal — 데이터 분석 파트 내부 모듈

팀 연동 형식(`analyze.py`, `contract/`, `api_spec.md`)과 **독립**된 분석·검증 코드입니다. 기존 파일을 수정하지 않고 `compare_rent.compare`만 읽기 전용으로 호출합니다.

| 경로 | 내용 |
|---|---|
| `engine_v2.py` | 0단계(같은 지번, 건축HUB 단일 건물 게이트) + 기존 1~3차 + 새 신뢰도 + 마진 가격 라벨 |
| `configs/candidate_v2.json` | 정책·통과 기준 (해시를 매 실행 매니페스트에 기록) |
| `configs/trust_coef_v2.json` | 신뢰도 로지스틱 고정 계수 (설계 6개 구로 학습) |
| `evaluation/run_backtest.py` | 기존 방식과 v2를 같은 기준 매물에서 비교하는 하네스 (`--frozen` 은 홀드아웃 1회 평가용) |
| `evaluation/leakage_checks.py` | 누수·중복 자동 검사 |
| `evaluation/prepare_holdout.py` | 송파·강북 정제와 기준 매물 선정 (성능 계산 없음) |
| `experiments/` | 시점 추세, 확률 재보정, 입력 오류 주입 실험 |
| `PREREGISTRATION.md` | 송파·강북 평가 전 고정한 정책·해시·통과 기준과 평가 결과 |
| `results/` | 실행별 `report.json`, `manifest.json` (계약 단위 `records.csv` 는 저장소에 올리지 않음) |

데이터(`output/clean_rent_data.csv`, `data/`)는 저장소에 없으며 `collect_rent.py`, `run_validation.py`, `collect_lot_buildings.py` 로 다시 만듭니다. API 키는 저장소에 없습니다.
결과 해설은 상위 폴더의 `분석결과_6개구.md`(18~26절)와 `프로젝트_요약.md` 를 보세요.

## 로컬 시연 (`demo/`)
`demo/실행.bat` 을 실행하면 `http://127.0.0.1:8765/` 에서 값을 직접 입력해 분석해 볼 수 있습니다(현재 정책 v2, 강서·관악·광진·노원·동작·마포구만).
지번을 넣으면 같은 건물 비교(0단계)를 시도하며, 건축물대장 동수는 캐시에 없으면 로컬 키 파일로 즉시 조회합니다(키는 서버 안에서만 사용). 이 PC 안에서만 열립니다.
