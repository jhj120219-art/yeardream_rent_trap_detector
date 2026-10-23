# utility — 관리비 점검 (전기 · 수도 · 가스 · 인터넷 참고 비용)

| 파일 | 역할 |
|---|---|
| `tariffs.py`, `tariff_data/tariffs_2026-10.json` | 요금 단가. 값마다 출처와 확인 상태(VERIFIED / PARTIAL / ASSUMPTION) |
| `calc.py` | 사용량 → 월 요금 (전기 누진 · 연료비조정 · 기후환경 · 기금 · 부가세, 가스, 수도 · 하수도) |
| `reference.py` | 가구에너지패널 14차(2023) 서울 결과표 기반 참고 사용량 · 요금 (주택유형 · 가구원수 · 면적 관점별) |
| `micro_ref.py` | 조건별 분포표가 로컬에 있을 때만 분위수 참고값 제공. 없으면 `None` 이고 `reference.py` 값으로 동작 |
| `recent_ref.py`, `recent_data/` | 최근 공개자료(한전 2025 · 가스공사 2024) 병기. 기본 추정을 바꾸지 않음. 갱신: `python -m utility.recent_load` |
| `check.py` | 상태 판정 `REFERENCE_ONLY` / `REVIEW_REQUIRED` / `INSUFFICIENT_DATA`. 정상 · 과다를 확정하지 않음 |
| `adapter.py` | 광고 판독 결과 → 표준 구조 변환: 금액 정수 원(Decimal), 포함 여부 · 부과 방식 · 계량 방식을 항목마다 따로, 충돌 표시, 사용자 확인 반영 |
| `integration.py` | `run_maintenance(payload)`: 광고 추출 → 사용자 확인 → 계산 → 결과 JSON(`maintenance.v1`) 하나. 모르는 조건은 가정하지 않고 보류 |
| `backend_options.py` | 백엔드 FIVE_ITEMS_V1 입력(만원 · SEPARATE_CHARGE · internet_status · OTHER · 예전 청소/공용) → 표준 광고 구조. 반올림 없이 검증 오류로 알림 |
| `data_files.py` | 필요한 데이터 파일 위치와, 없을 때 이름 · 위치 · 만드는 방법을 알리는 오류(`MissingDataFile`) |
| `contract_tests/`, `test_contract.py` | 골든 파일 계약 시험: 백엔드 입력 JSON → 결과의 안정 보기 고정 (`--update`로 기대값 갱신: 눈으로 확인한 뒤에만) |
| `examples/` | `run_maintenance` 입력 · 출력 예시 4쌍 (정상 / 계량 미확인 보류 / 조건 부족 / 자료 없음) |
| `demo/` | 시험판 화면 (`run_utility_demo.bat`, 포트 8766): 항목별 참고 비용 · 관리비 구성 보기 · 확인 질문 |
| `test_*.py` | 계산 · 시나리오 · 안전 규칙 · 변이 · 적대 입력 시험 |
| `bill_eval_template.csv` | 실제 고지서 평가셋 양식 (개인정보 제외) |

## 지켜야 할 표현

- 공용 관리비는 '기타'. "부당" · "과다 청구" · 빨간 경고 사용 금지. 총액 − 추정합계를 부당액으로 해석하지 않음.
- 결과에는 사용한 집단 · 기준 연도 · 가정을 함께 표시. 집단 평균의 최소~최대를 "정상 범위"라고 부르지 않음.
- 포함 여부 · 계량 방식 · 난방이 불명확하면 가상 구성을 만들지 않고 보류.

검증 수준과 한계: [`../../docs/maintenance_validation.md`](../../docs/maintenance_validation.md)