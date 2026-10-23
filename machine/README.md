# machine — 데이터 분석 · 참고 비용 계산 모듈

AI 월세 함정 탐지기의 **데이터 분석 담당 영역**입니다. 두 가지를 합니다.

| 영역 | 하는 일 | 상태 |
|---|---|---|
| **월세 시세 비교** | 서울시 실거래 데이터에서 비슷한 계약을 찾아 월세의 위치와 신뢰도를 계산 | 완성 · **서비스에서 계속 사용** (백엔드가 호출 중) |
| **관리비 점검** | 광고 관리비에 들어 있는 전기·수도·가스·인터넷의 **참고 비용**을 서울 비슷한 가구 기준으로 계산 | 계산·판독 모듈과 통합 함수 `run_maintenance()` 완성(백엔드 5항목 입력 변환 포함) · 백엔드 실제 호출 시험 전 |

> 이 모듈은 사기·부당·과다 청구를 **판정하지 않습니다.** 결과 상태는 `REFERENCE_ONLY`(참고) / `REVIEW_REQUIRED`(확인 필요) / `INSUFFICIENT_DATA`(자료 부족)뿐이고, 모든 금액은 "참고 추정값"이며 사용한 집단·기준 연도·가정을 함께 돌려줍니다.

## 폴더 구조

```
machine/
├── analyze.py              월세 분석 진입점  analyze_listing(payload, pool)
├── compare_rent.py         정제 · 유사 거래 1~3차 탐색 · 신뢰도
├── normalize_listing.py    입력 변환 (별칭 · 단위 · 층 · 확인 규칙)
├── collect_rent.py         서울 열린데이터광장 전월세 수집 (원본)
├── prepare_clean_data.py   원본 정제 -> output/clean_rent_data.csv (비교 풀, output 폴더 자동 생성)
├── check_data.py           필요한 데이터 파일이 있는지 점검, 없으면 이름 · 위치 · 만드는 방법 안내
├── api_spec.md             연동 규격
├── contract/               연동 계약 v1.1 + 상태별 예시 JSON
├── integration_kit_v1.1/   광고 이미지 분석용 프롬프트 · 예시 · 상태 사전
├── test_analyze.py         월세 엔진 테스트
├── test_normalize.py       입력 변환 테스트
├── analysis_internal/
│   ├── engine_v2.py, common.py, configs/   내부 분석 엔진 v2 (백엔드가 사용)
│   ├── utility/            관리비 점검: 요금 계산 · 참고 사용량 · 상태 판정 · 시험판 화면
│   └── extraction/         광고 문구 · 목록/상세보기 구조화
└── docs/                   검증 요약 · 데이터 출처와 이용 조건
```

> 백엔드(`backend/`)가 직접 불러 쓰는 경로입니다. **이동·이름 변경 전에 백엔드 담당과 협의하세요:** `analyze.py`, `compare_rent.py`, `normalize_listing.py`, `test_normalize.py`, `api_spec.md`, `contract/`, `integration_kit_v1.1/`, `analysis_internal/engine_v2.py`, `common.py`, `configs/`.

## 빠른 시작

Python 3.10+, `pandas`, `numpy` (수집 시 `requests`, 결과표 변환 시 `openpyxl`).

### 먼저: 필요한 데이터 파일 확인

코드는 아래 데이터 파일이 있어야 계산합니다. **저장소에는 올라가 있지 않으므로** 먼저 점검하세요. 없으면 어떤 파일이 없고 어떻게 만드는지 알려 줍니다.

```bash
python check_data.py        # (machine/ 에서) 없는 파일의 이름 · 위치 · 만드는 방법 출력. 파일을 바꾸지 않음
```

| 파일 | 쓰임 | 준비 방법 |
|---|---|---|
| `output/clean_rent_data.csv` | 월세 비교 풀 | `collect_rent.py`로 구별 원본을 받고 `python prepare_clean_data.py` (output 폴더는 자동 생성). 서버(백엔드)는 자체 DB를 쓰면 필요 없음 |
| `data/utility_stats/energy_reference_2023.csv` | 관리비 점검 참고 사용량 (가구에너지패널 14차 결과표) | **(A) 파일을 받아 두기**: 아래 경로 중 한 곳에 두거나 환경변수 `ENERGY_REFERENCE_CSV=<경로>` (서버 · 도커는 이 방법이 편함). **(B) 직접 만들기**: KESIS 결과표 엑셀 4개를 `data/utility_stats/keei/hep14/`에 두고 `python analysis_internal/utility/parse_hep14.py` |

`energy_reference_2023.csv`를 찾는 순서: 환경변수 `ENERGY_REFERENCE_CSV` → `machine/data/utility_stats/` → `analysis_internal/utility/reference_data/`. 서울 가구 표만 쓰므로 서울만 담은 작은 파일(약 1,000행)도 그대로 동작합니다. 파일이 없을 때 `run_maintenance()`는 멈추지 않고 결과의 `errors`에 `MISSING_DATA_FILE`과 만드는 방법을 담아 돌려줍니다.

### 테스트

```bash
# 월세 엔진 테스트 (machine/ 에서)
python test_analyze.py
python test_normalize.py

# 관리비 점검 테스트 (machine/analysis_internal 에서)
python -X utf8 -m utility.test_utility
python -X utf8 -m utility.test_scenarios
python -X utf8 -m utility.test_tariff_data
python -X utf8 -m utility.test_independent_calc
python -X utf8 -m utility.test_recent
python -X utf8 -m utility.test_adapter           # 단위 변환 · 통합 함수 경계 사례
python -X utf8 -m utility.test_backend_options   # 백엔드 5항목 변환 · 기본 동작(나머지 금액 꺼짐, 상태 의미)
python -X utf8 -m utility.test_contract          # 골든 파일 계약 시험(백엔드 입력 -> 결과)
python -X utf8 -m utility.test_data_files        # 데이터 파일이 없을 때 안내(데이터 없이도 실행)
python -X utf8 -m utility.test_safety_combos     # 약 13분
```

관리비 시험판 화면: `analysis_internal/utility/demo/run_utility_demo.bat` → http://127.0.0.1:8766

## 1. 월세 시세 비교

- 입력은 계약 v1.1(`contract/analysis_contract_v1.1.json`), 출력은 가격 위치·비교 근거·신뢰도 등급·확인할 항목입니다. 상태별 예시는 `contract/examples/`.
- 서울시 `tbLnOpendataRentV`(공공누리 1유형)의 **신규 월세 계약**만 사용합니다. 광고 호가가 아니라 체결 계약 기준입니다.
- 지원: 아파트 · 연립다세대 · 오피스텔 · 단독다가구, 검증한 자치구만. 단독다가구는 층 정보가 없어 층을 사용자가 확인했을 때만 제한적으로 판정합니다.

| 검증 (요약) | 결과 |
|---|---|
| 설계 6개 구 백테스트 (8,995건) | 중앙 오차 16.7%, 신뢰도 높음 / 보통 / 낮음 = 11.9 / 20.0 / 28.3% |
| 서대문 · 성북 홀드아웃 (규칙 고정, 사전 기준 7개) | 7개 모두 통과 |
| 송파 · 강북 홀드아웃 (내부 엔진 v2, 1회 평가) | 사전 기준 7개 모두 통과, 개선 폭은 작음 (17.86 → 16.67%) |

세부 조건과 한계는 [`docs/rent_validation.md`](docs/rent_validation.md).

## 2. 관리비 점검

광고의 관리비 안에 전기·수도·가스·인터넷이 **포함**돼 있을 때, 같은 조건 서울 가구의 참고 비용을 보여 줍니다. 공용 관리비는 '기타'로 두고 판단은 사용자가 합니다.

- **요금 계산** (`utility/calc.py`, `tariffs.py`, `tariff_data/`): 한전 주택용 누진 · 서울도시가스 · 아리수 요금표. 값마다 확인 상태(VERIFIED / PARTIAL / ASSUMPTION)와 출처를 기록.
- **참고 사용량** (`reference.py`, `micro_ref.py`): 가구에너지패널 14차(2023) 서울 결과. 가구원 수 · 면적 · 주택유형 관점별로 따로 보여 주며 서로 곱하지 않습니다.
- **상태 판정** (`check.py`): 항목별 청구액이 있을 때만 비교, 포함 여부 · 난방 · 계량 방식이 불명확하면 보류.
- **최근 공개자료 병기** (`recent_ref.py`): 한전 2025 월별 서울 주택용 · 가스공사 2024 서울 가구당 소비량. 추세 참고용이며 기본 추정값을 바꾸지 않습니다.
- **광고 구조화** (`extraction/`): 상세보기 · 목록 문구에서 금액 · 포함/별도 · 실비 여부를 규칙으로 읽습니다. 이미지는 OCR 후 **사용자 확인이 필수**입니다.
- **통합 함수** (`utility/integration.py`, `adapter.py`): 위 단계를 하나로 잇습니다.

### 통합 함수 `run_maintenance(payload)`

광고 입력 → 사용자 확인 → 계산 → 결과 JSON(`maintenance.v1`) 하나로 돌려줍니다. 입력은 두 가지입니다.

```python
from utility.integration import run_maintenance      # machine/analysis_internal 이 import 경로에 있을 때
conditions = {"target_month": 10, "household_size": 1, "housing_type": "다세대·연립", "area_m2": 20}

# (1) 백엔드의 5항목 입력(FIVE_ITEMS_V1)을 그대로: 만원 단위, SEPARATE_CHARGE, internet_status 등
result = run_maintenance({"contract_version": "FIVE_ITEMS_V1", "backend_options": options,
                          "user": {"confirmed": True, "metering": "INDIVIDUAL"}, "conditions": conditions})
# (2) 광고 화면 글자를 읽은 결과
result = run_maintenance({"ad_text": "<상세보기 글자>", "conditions": conditions})     # 또는 "ad": parse_detail 출력(dict)
```

- **백엔드 5항목 변환** (`backend_options.py`): 만원 → 정수 원(Decimal), `null`은 `null` 유지(0원은 무료가 명시된 경우만), `SEPARATE_CHARGE` → `SEPARATE`, `internet_status`의 `AVAILABLE`/`NOT_AVAILABLE`은 이용 가능 여부만 기록하고 포함 여부는 `UNKNOWN`. 1원 미만이 생기는 값(8.12345만원)이나 문자열("8만원")·음수는 반올림하지 않고 `errors`로 알립니다.
- **기타(OTHER)는 광고에 명시된 금액만** 담습니다(`items.OTHER`). 청소·공용·주차는 설명(`descriptions`)으로만 두고, **총액에서 다른 항목을 빼서 기타 금액을 만들지 않습니다.** 예전 청소·공용 세부내역은 `legacy_components`로 보존할 뿐 합치지 않습니다. 총액에서 역산한 "나머지 금액"(`decomposition`)은 기본으로 꺼져 있고, 내부 확인용으로 `experimental_remainder: true`일 때만 계산합니다.
- **항목마다 세 가지를 따로 둡니다.** 포함 여부(`INCLUDED` / `SEPARATE` / `UNKNOWN`), 부과 방식(`FIXED` / `ACTUAL` / `MIXED`), 계량 방식(`INDIVIDUAL` / `SHARED` / `UNKNOWN`). "실비"는 부과 방식일 뿐 개별 계량의 증거가 아니라서 계량 방식은 사용자가 확인해야 바뀝니다.
- **모르는 조건은 임의로 가정하지 않고** 그 관점을 건너뛴 뒤 `missing_fields`와 `confirmation_questions`로 알립니다.
- **상태 의미**: `REFERENCE_ONLY`(참고 정보를 표시) / `REVIEW_REQUIRED`(**광고에서 읽은 정보나 입력값을 확인해야 함**: 포함+별도 충돌, 읽기 불완전, 항목 금액 합이 총액보다 큼) / `INSUFFICIENT_DATA`(참고 계산에 필요한 정보 부족). 광고 금액이 참고 구간보다 크다는 이유로 상태를 올리지 않고, 그 차이는 상태와 별개인 `reference_comparison`에 사실(광고 금액 · 참고 구간 · 비율 · 한계)로만 기록합니다.
- **오류 구분**: 서버 환경 오류(`MISSING_DATA_FILE`)와 입력 검증 오류(`INVALID_INPUT` / `INVALID_AMOUNT` / `INVALID_STATUS` / `UNSUPPORTED_CONTRACT_VERSION`)는 `errors`에 담고, 사용자가 정보를 덜 입력한 경우와 구분합니다. 모든 결과에 `schema_version`, `source_contract_version`, `calculation_version`, `tariff_version`, `assumptions`가 들어갑니다.
- 결과: `status`, 항목별 참고 비용(`utility_estimates`), 별도 납부 항목(`separate_items`), `reference_comparison`, `items.OTHER`, `reason_codes`, `errors`, `assumptions`.
- 입력·출력 예시 5쌍: [`analysis_internal/utility/examples/`](analysis_internal/utility/examples/). 골든 파일 계약 시험(`test_contract`): `utility/contract_tests/` (정상 · 포함+별도 · 인터넷 이용 가능 · 무료(0)와 미확인(null) · 기타만 · 모순 · 데이터 파일 누락 · 지원하지 않는 버전). 백엔드 연동 규격(`contract/` v1.1)은 합의 전이라 바꾸지 않았습니다.
### 관리비 항목 구성: 5항목 + '기타' (팀 확인 필요한 제안)

기본 항목은 **전기 · 수도 · 가스 · 인터넷 · 기타** 5개입니다. 청소 · 경비 · 승강기 · 공용전기 등 공용 관리비는 모두 **'기타'**로 모읍니다. 현재 `decomposition`의 "참고 가정에 따른 나머지 금액"이 '기타'에 해당합니다.

- 아파트에 청소 · 공용 항목을 따로 추가하지 않고 **'기타' 하나로 통일**하는 것을 권합니다. 주택유형(아파트 / 빌라 / 다가구 / 오피스텔)마다 항목 구성이 달라지면 화면 · 백엔드 · 결과 JSON이 갈라지기 때문입니다.
- 빌라 · 다가구 · 오피스텔은 청소 · 공용이 건물별 정액이고 항목별 공개 통계가 없어 '기타' 하나로만 보여 줄 수 있습니다.
- 아파트는 국토부 K-apt 관리비 API가 공용관리비를 17개 항목(인건비 · 청소비 · 경비비 · 승강기 유지비 등)으로 공개합니다. 실험(서울 단지 60개, 단지 평균)에서 같은 단지 과거값은 오차 1.7%, 비슷한 단지는 16.6%(기준선 22.1%)였습니다. 이것을 쓴다면 **'기타'의 하위 상세(선택 표시)**로 두고 새 최상위 항목으로 늘리지 않는 구조가 맞습니다. 아직 서비스에는 연결하지 않았습니다.
- 광고 상세보기에 청소 · 공용이 따로 적혀 있으면(`공용`, `기타` 금액) 읽은 금액을 '기타'의 광고상 금액으로 보여 줍니다.

결정이 필요한 점: (1) '기타' 하나로 통일 vs 아파트에만 세부 항목 추가, (2) 아파트 K-apt 단지 참고값을 '기타' 하위로 연결할지(주소 → 단지 매칭 필요).

검증 수준과 아직 주장하면 안 되는 것은 [`docs/maintenance_validation.md`](docs/maintenance_validation.md)에 정리했습니다.

## 한계 (먼저 읽어 주세요)

- 개별 가구의 **실제 공과금 예측 정확도는 검증하지 않았습니다.** 실제 고지서 평가는 자료 확보 후 진행합니다.
- 서울 원룸 관리비의 "정상 범위"나 부당 관리비 탐지 정확도는 주장할 수 없습니다.
- 가구에너지패널은 2023년 조사이고 소형 가구 칸은 표본이 작습니다. 마이크로데이터 파생 분포는 이용 범위 확인 전이라 저장소에 없으며, 없을 때는 공개 결과표 기반 참고값으로 동작합니다.
- 미확정 가정: 기후환경요금 9원/kWh, 전력산업기반기금율 2.7%. (도시가스 열량은 한국가스공사 서울도시가스 12개월 평균 42.6MJ/N㎥로 확인됨)
- 월세 비교는 6~10개 자치구 검증이고, 옵션 · 관리비 · 건물 상태는 데이터에 없습니다.

## 데이터와 라이선스

출처와 이용 조건은 [`docs/data_and_licenses.md`](docs/data_and_licenses.md). 원본 데이터, 인증키, 실제 광고 캡처, 가구에너지패널 마이크로데이터와 그 파생 분포는 저장소에 올리지 않습니다. 코드 라이선스는 팀 합의 후 `LICENSE`로 추가합니다.
