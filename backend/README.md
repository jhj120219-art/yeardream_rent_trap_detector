# 월세 비교 백엔드 — 기존 분석 코드 연동

> **다른 장소 팀 연결:** [공유 서버 안내](TEAM_SERVER.md). 별도 테스트 DB·접속키 보호·임시 HTTPS 경로를 추가했다. 공유 모드에서는 관리비·공과금 API를 503으로 차단하고 통합 보고서의 관련 비용 항목을 ON_HOLD로 반환한다. 기존 개인 DB와 로컬 개발 모드는 보존한다. 상시 운영 배포와 구분한다.

> **현재 팀 통합 범위(2026-10-19 개정):** 관리비·공과금 자료는 분석 담당 검증 중으로 참고 견적 추가 개발·화면 연동을 보류합니다. 기존 API·DB는 보존돼 있으므로 응답에 관련 필드가 있어도 자료 검증 완료로 간주하지 마세요. 프론트는 property/rent 중심의 직접 입력→확인→등록→월세 분석→결과 조회부터 연결하고 관련 참고 금액·견적·workflow 안내 노출은 제외해 주세요. 아래 공과금 구현 기록은 기존 기술 설명이며 현재 출시 승인 상태가 아닙니다.

## 공과금 참고 견적 연결 — 2026-10-19

월세 분석 결과와 별도로 `POST /listings/{id}/utility-estimates`에서 참고 견적을 저장한다. 기존 Bearer 세션을 사용한다. `GET /utility-estimates/{id}` / `DELETE /utility-estimates/{id}`로 조회·삭제하며 매물/세션 삭제 시 함께 삭제된다. `GET /listings/{id}/report`의 `utility_estimate`에는 마지막 저장 견적이 포함된다(없으면 null). `utility_costs`는 광고 포함 여부, `utility_estimate`는 사용자가 조건을 선택해 생성한 견적 스냅샷이다. GET 요청만으로 계산·저장·유료 외부 호출하지 않는다.

`GET /utilities/reference-catalog`에서 지원 조건·공개 통계 프로필·출처를 확인한다. 현재 버전은 2026년10~12월의 비하계 참고 시나리오만 지원한다. 기초 전기요금표는2024-07-01, 기후9원/kWh·연료5원/kWh·부가세10%·기금2.7% 가정이며 실제 청구서 인증 계산기가 아니다. 가스는 서울도시가스 서울지역2026-10-01 요금표를 사용한다. 요금 갱신을 자동 수행하지 않으므로 지원기간 밖 요청은422이며 새 적용분 검토·버전 갱신이 필요하다.

등록 예시:

```json
{
  "scenario_month": "2026-10",
  "acknowledge_reference_limits": true,
  "use_public_reference": true,
  "electricity_contract": "LOW_VOLTAGE",
  "gas_supplier": "SEOUL_CITY_GAS_SEOUL",
  "household_size": 1,
  "water_individual_meter": true,
  "water_meter_mm": 15,
  "internet_plan": "KT_SLIM_100M_3Y"
}
```

사용자는 과거 통계/요금 가정임을 확인하고 전기 계약·가스 공급사·수도 계량기 조건을 실제에 맞게 선택해야 한다. `acknowledge_reference_limits`나 매물 사용자 확인이 없으면 숫자를 생성하지 않는다. `use_public_reference` 기본false. 직접 사용량을 아는 경우 `electricity_kwh`(월kWh,0~1000), `gas_mj`(월열량MJ), `water_m3`(월㎥)를 지정하면 통계보다 우선한다. m³ 가스 검침량을 MJ 입력칸에 넣지 않는다. 월세/관리비 입력은 기존대로 만원이며 이 견적의 금액 응답 필드는 이름대로 **원**이다.

| 항목 | 사용 근거·필요 조건 |
| --- | --- |
| 전기 | 서울 아파트 또는 다세대/연립/기타의2023년 연간kWh÷12. 비하계 저압 확인 필요. 직접 사용량은 유형 통계가 없어도 가능 |
| 가스 | 같은 표의 연Mcal×4.1868÷12를 월MJ로 환산. 서울도시가스 서울권역 확인 필요. 겨울 예측 아님 |
| 수도 | 서울1인세대2021년 일264L×30일=7.92㎥. 다른 가구원 수는 현재 통계 자동적용 안 함. 직접사용량 가능. 개별15mm미확인이면 변동요금 부분만 제공하고 총액 보류 |
| 인터넷 | KT100M슬림3년약정 표준월요금22000원 예시. 상품 명시 선택 필요. 단체계약/할인/공유기/설치비 제외 |

아파트 프로필을 빌라로, 다세대/연립/기타 프로필을 오피스텔로 치환하지 않는다. 현재 프로필은 서울 시도 단위이며 동별·평당·현재 개별 평균이 아니다. 면적/동주소를 변경해도 같은 광역 프로필은 동일하다는 한계를 표시해야 한다. 원본통계ZIP 없이도 사실 요약값·출처가 코드에 있어 다른 PC에서 참고 계산을 재현할 수 있다. 실거래 데이터 준비는 기존대로 별도다.

`items[].state`: ESTIMATED, INCLUDED_IN_MAINTENANCE, INPUT_REQUIRED, NO_MATCHED_REFERENCE, UNSUPPORTED_REGION, PARTIAL_ONLY, NEEDS_REVIEW. `estimated_monthly_won`은 참고 계산액, `additional_to_maintenance_won`은 별도 부담으로 확인된 추가액이다. 포함이면 추가액0(실제 사용료0원이라는 뜻이 아님), 미기재면 참고액이 있어도 추가액null. 모든 항목의 추가액과 입력 월세/관리비가 확인됐을 때만 `scenario_monthly_subtotal_won`을 제공한다. 주차·일회성 비용은 제외하므로 전체 생활비라고 표시하지 않는다.

프론트용 실제 API 출력 예시: `backend/examples/utility_estimates.json`(가상 입력, 정확도 검증 아님). 빌라 참고 계산, 오피스텔 통계 없음, 수도 포함 여부 미상, 사용자 확인 필요의4종이다. 출처·통계연도·조건·계산식·보류사유를 함께 표시하고 월세 가격 막대/판정과 합치지 않는다.

## 전체 통합 담당자 전달 사항 — 2026-10-19

프론트 연결 순서: `/sessions` → `/addresses/search` 또는 `/extractions` → `/extractions/{id}/listing-draft` → 확인·수정한 `draft`로 `/listings` → `/listings/{id}/analyses` → `/listings/{id}/report`. 모든 개인 자료 API에 같은 Bearer 세션을 사용한다. 주소는 검색 후보를 사용자가 선택한 뒤 코드를 폼에 복사한다. 이미지 초안의 주소 코드·호수·기준일은 임의 추정하지 않는다. 주소/이미지 키 없이도 직접 입력은 가능하다.

`GET /extractions/{id}/listing-draft` 응답은 `draft`, `extraction_status`, `missing_or_unknown_fields`, `source_fields`, `notice`로 구성된다. `draft`는 기존 등록 API 형태이며 확인 상태는 항상 false다. 필수값을 채우고 사용자 확인 후 등록한다. MULTIPLE_LISTINGS 등은 값을 폼에 자동 채우지 않는다. `source_fields`는 읽은 문구를 검토용으로 보여주는 자료이며 그대로 등록 body에 추가하지 않는다. 실제 AI 호출 검증은 별도다.

전체 결과의 `utility_costs.items`에 ELECTRICITY/GAS/WATER/INTERNET을 제공한다. 각 항목은 `advertised_status`, `confirmed`, `additional_to_maintenance_10k_krw`, `reference_monthly_10k_krw`, `reference_state`, `action`을 가진다. 포함이라고 명시되고 사용자 확인된 항목만 추가 비용을 0으로 표시한다(실제 사용료 0원이 아님). AVAILABLE은 요금 포함을 의미하지 않는다. 미기재·별도는 추가 금액 null. 참고 통계는 미연결이므로 금액 null/NO_MATCHED_REFERENCE이며 동네·평수에 임의 상수를 곱하지 않는다.

### 프론트 담당 요청 초안

1. 직접 입력과 캡처 검토를 같은 매물 입력 화면에 연결해 주세요. 캡처는 초안이며 확인 전 분석하면 안 됩니다.
2. 결과 화면을 매물/월세 비교/관리비/옵션/공과금/월 지출 소계로 나눠 주세요. 소계는 전체 생활비가 아닙니다.
3. 공과금은 포함/별도/미기재를 표시해 주세요. 인터넷 가능을 무료로 표시하지 말고, 참고 금액 null을 0원으로 바꾸지 마세요.
4. 정상/확인 필요/참고용/자료 부족/설정 미완료/세션 만료를 구분해 주세요. 가격 차이율은 기존 계약의 비율(예: 0.6)을 화면에서 60%로 표시합니다.
5. 로컬 시연 주소는 127.0.0.1:8011이며 같은 PC에서만 접속됩니다. 별도 PC의 localhost는 연결되지 않습니다. 팀 통합에 사용할 실행 PC/배포 주소를 정한 뒤 CORS와 서버 주소를 맞춰야 합니다. 완료 여부는 실제 시연으로 확인할 예정입니다.

### 분석 담당 요청 초안

1. 서비스에 연결할 최종 분석 코드/버전과 실행 방법·필요 파일을 전달해 주세요. 시연 화면만으로는 백엔드 연결을 확인할 수 없습니다.
2. 같은 건물 우선 → 주변 확대가 구현된 버전인지, 현재 동→조건 완화→구 방식인지 확정해 주세요. 건물 판별에 필요한 입력과 건물용도 혼합 방지 검증도 부탁드립니다.
3. 비교 거래 목록을 반환할 수 있는지 확인해 주세요. 가능하면 개인정보 없는 거래 식별자, 계약일, 건물유형, 면적㎡, 보증금/월세 만원, 층, 비교 범위·선정 이유를 포함한 입출력 예시를 부탁드립니다. 현재 서비스 응답에는 개별 목록이 없습니다.
4. 기준 가격 범위·중앙값·차액/차이율·표본 수·신뢰도·보류 사유의 기존 계약을 유지할 수 있는지, 변경이 필요하면 차이와 예시를 알려 주세요. 관리비/옵션 때문에 월세 계산을 임의 변경하지 않습니다.
5. 공과금 참고값 자료가 이미 있으면 지역·주택유형·면적·계절·가구원/난방 조건·표본 수·출처·단위가 있는 자료를 공유해 주세요. 새 공과금 모델을 필수 개발로 요청하는 것은 아닙니다. 자료가 없으면 미연결로 유지합니다.

공과금 근거 검토: [K-apt](https://www.k-apt.go.kr/)는 공개 대상 공동주택의 관리비 자료이며 모든 원룸/빌라에 적용되는 동네 평균으로 간주하지 않습니다. [가구에너지패널 연구](https://kesis.keei.re.kr/boardDownload.es?bid=0010&list_no=579&seq=1)는 면적·가구원·난방/에너지원 등의 구분을 다룹니다. 현재 원룸·오피스텔·빌라의 동별·평당 가스/전기/수도/인터넷 월요금 평균을 확보·검증한 상태가 아닙니다. 자료 연결 전까지 참고 숫자는 제공하지 않습니다.

> **최신 로컬 데이터 상태(2026-10-19):** 서울시 공식 Sheet CSV 내려받기로 접수연도 2026인 461,550행을 키 없이 추가 확보했습니다. 기존 2025 자료와 합쳐 지원 6개 구의 정제 월세 305,674건, 신규 비교 풀 **238,090건**을 로컬 기본 경로에 연결했습니다. 계약 최신일은 **2026-10-16**입니다. 이전 2025 전용 파일은 backend/data/snapshots/에 보존했습니다. 실제 자료 기반 대표 3유형 시험과 75개 회귀 테스트를 통과했습니다. 아래 2025 최초 연결 기록은 이 상태로 갱신됩니다. 데이터는 공개 Git에 없으므로 다른 PC에는 별도로 준비해야 합니다.

올해 자료는 공식 데이터 페이지의 Sheet CSV 내려받기 기능입니다. 다운로드 시점의 접수연도와 행 수를 검증해야 하며 미리보기 1,000행만으로 전체 자료를 대체하지 않습니다. prepare_seoul_file은 FILE ZIP과 Sheet CSV를 모두 받을 수 있고 `--year 2026`으로 접수연도를 확인합니다. 이 명령의 `--zip` 인자는 호환성을 위해 이름을 유지했으며 CSV 경로도 허용합니다.

> 2026-10-19 실제 자료 연결: 서울시 공식 FILE 다운로드의 `서울특별시_전월세가_2025.zip`을 받아 기존 정책의 6개 구 자료를 정리했습니다. 로컬 `backend/data/clean_rent_data.csv`에 신규 비교 대상 162,689건을 연결했습니다. 데이터는 Git에 포함하지 않으므로 다른 PC에서는 별도 준비가 필요합니다. 파일의 계약일은 정제 전체 기준 2023-09-18~2026-01-21이며, '2025' 파일명은 계약일 전체가 2025년이라는 뜻이 아닙니다. 최신 시세로 표시하지 마세요. 오늘 기준 요청에서 DATA_STALE을 확인했습니다. 아래 ZIP에 데이터가 없다는 설명은 전달받은 팀 코드 ZIP에 관한 설명입니다.

공식 다운로드: [서울시 부동산 전월세가 정보](https://data.seoul.go.kr/dataList/OA-21276/A/1/datasetView.do)의 FILE 항목. 서울시 공공누리 제1유형 출처표시 조건을 유지합니다.

공식 FILE ZIP을 별도로 받을 때에는 아래처럼 한글 열만 기존 수집기 형식으로 연결한 뒤 원래 정제 코드를 사용합니다. 첫 명령은 기존 출력 파일을 덮어쓰지 않습니다. 기존 정상 데이터는 별도 보존하고 새 경로에서 검증하세요.

```bash
python -m backend.scripts.prepare_seoul_file --zip backend/data/incoming/seoul_rent_2025.zip --out backend/data/incoming/seoul_2025_six_raw.csv
python -m backend.scripts.import_data --raw backend/data/incoming/seoul_2025_six_raw.csv --out backend/data/seoul_2025_six_clean.csv
```

회의 내용과 `contract/analysis_contract_v1.1.json`, `api_spec.md`, `integration_kit_v1.1/`에 맞춘 웹 API입니다. 변경 파일은 `backend/` 안에만 있습니다. 가격·신뢰도 계산을 다시 만들지 않고 루트의 `normalize_listing.analyze_raw()` → `analyze.analyze_listing()`을 호출합니다.

## 1. 실행 (Python 3.10 이상, 저장소 루트)

```bash
python -m venv backend/.venv
# macOS/Linux
source backend/.venv/bin/activate
# Windows PowerShell에서는 backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements-dev.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

- API 문서: http://127.0.0.1:8000/docs
- 상태 확인: http://127.0.0.1:8000/health
- 테스트: `python -m pytest backend/tests -q -p no:cacheprovider`
- `.env.example`은 설정 예시입니다. 파일을 복사하는 것만으로 자동 적용되지 않습니다. 실행 환경에 변수를 등록하세요. PowerShell: `$env:OPENAI_API_KEY="..."`, bash: `export OPENAI_API_KEY="..."`.
- SQLite DB 기본 위치: `backend/data/app.sqlite3`. 매물 원본 입력, 추출 텍스트, 분석 결과를 저장합니다. 운영 키·DB·실거래 CSV는 커밋하지 않습니다.

## 2. 실거래 데이터 연결

**제공된 ZIP에는 `output/clean_rent_data.csv`와 원본 실거래 자료가 없습니다.** 데이터 없이 서버·입력 저장은 실행되며, 분석 요청에는 503을 반환합니다. 가짜 시세를 운영 데이터로 채우지 않습니다.

분석 담당자가 이미 만든 정제 CSV가 있다면 그 경로를 `RENT_CLEAN_CSV`로 지정하고 서버를 시작하세요. 기본은 `backend/data/clean_rent_data.csv`입니다. 루트의 `analyze.load_pool()`이 그대로 읽을 수 있는 형식이어야 합니다.

새로 수집할 때는 기존 수집기를 사용합니다. 예시는 관악구 2025~2026년이며, 실제 제공 범위는 수집 설정으로 결정됩니다.

```bash
# 환경변수 SEOUL_API_KEY 설정 후 (실제 키는 코드에 넣지 않음)
python collect_rent.py --years 2025 2026 --gu 11620 --out backend/data/rent_raw.csv
python -m backend.scripts.import_data --raw backend/data/rent_raw.csv
```

원본 → 기존 `compare_rent.clean()` → 임시 CSV 검증 → 정상일 때 정제 CSV 교체 순서입니다. 검증 실패 시 정상 파일을 유지합니다. **전체 스냅샷 교체** 방식이므로 다시 가져와도 행이 누적되지 않습니다. 동일한 조건의 실제 계약이 여러 건일 수 있어 기존 정책대로 중복 의심 행을 삭제하지 않습니다. 정정은 새 전체 원본을 다시 가져와 반영합니다. 여러 구를 서비스하려면 수집 명령에 필요한 모든 구를 지정하세요. 한 구만 수집한 파일로 교체하면 이전 구 자료가 유지되는 증분 병합이 아닙니다.

데이터는 시작할 때 한 번 읽으므로 교체 후 서버를 재시작합니다. 자동 수집 스케줄러·증분 정정 추적은 아직 없습니다. 실거래는 기존 코드와 맞춰 CSV로 관리하고, 개인 입력·결과는 SQLite로 관리합니다.

## 3. 프론트 연결 순서

1. `POST /sessions` → 발급받은 `token`을 해당 사용자의 세션으로 보관.
2. 이후 요청 헤더에 `Authorization: Bearer <token>`.
3. 주소 직접 입력 또는 `GET /addresses/search?q=...`로 후보 조회 → 사용자 선택.
4. 선택 기능: `POST /extractions`에 `multipart/form-data`의 `file`로 캡처 한 장 전달.
5. 추출값을 수정 가능한 폼에 반영. 자동으로 확인 완료 처리하지 않음.
6. 최종 입력을 `POST /listings`에 전달. 응답 `validation`에 확인 필요 항목 표시.
7. 반환된 `id`로 `POST /listings/{id}/analyses` 호출.
8. 응답의 **`result`**가 기존 분석 계약의 출력. `status`, `price_label`, `warnings`, `hold_reasons` 등을 그대로 표시.

기존 매물 입력은 수정하지 않는 스냅샷입니다. 수정·재확인은 `POST /listings`로 새 매물을 등록해 분석합니다. 따라서 이전 분석의 입력과 결과가 바뀌지 않습니다. 매물 삭제 시 해당 매물의 분석 결과도 함께 삭제됩니다.

### 등록 예시 (금액: 만원, 면적: ㎡)

```json
{
  "schema_version": "1.1",
  "listing": {
    "address_text": "사용자가 선택한 건물 주소",
    "building_dong": null,
    "unit_ho": "사용자가 직접 입력한 호수",
    "district_code": "11620",
    "legal_dong_code": "1162010100",
    "building_type": "APARTMENT",
    "area_m2": 59.9,
    "area_basis": "EXCLUSIVE",
    "deposit_10k_krw": 5000,
    "rent_10k_krw": 80,
    "built_year": 2005,
    "floor": 5,
    "floor_type": "GROUND",
    "floor_source": "USER_CONFIRMED"
  },
  "options": {"maintenance_10k_krw": 7, "internet_status": "UNKNOWN"},
  "confirmation": {
    "user_confirmed": true,
    "input_source": "ADDRESS_MANUAL",
    "confirmed_fields": ["address", "building_type", "area_m2", "area_basis", "deposit_10k_krw", "rent_10k_krw", "floor"]
  }
}
```

지역·금액은 형식을 보여주는 예시이며 실제 매물의 가격 적정성을 뜻하지 않습니다. 법정동 코드 대신 `dong`을 입력할 수도 있습니다. 건물 동(`building_dong`), 법정동(`dong`), 호수(`unit_ho`)를 구분하세요. 호수는 보관만 하고 공개 실거래의 동일 호실을 특정하는 데 사용하지 않습니다.

| API | 동작 |
| --- | --- |
| `GET /health` | 서버 상태, 데이터 READY/MISSING/INVALID |
| `GET /capabilities` | 실제 로드한 신규 계약의 구·유형·지하 여부별 건수, 주소/이미지 설정 여부, 미지원 기능 |
| `GET /ready` | 분석용 데이터가 없으면 503 |
| `POST /sessions` | 사용자별 임시 세션 발급 |
| `DELETE /sessions/current` | 해당 세션 및 보관 자료 전체 삭제 |
| `GET /addresses/search?q=...` | 카카오 주소 후보·법정동 코드 조회 |
| `POST /listings` | 입력·확인 상태·정규화 결과 저장 |
| `GET /listings?limit=20&offset=0` | 본인 매물 목록, 최대50개/요청, has_more로 다음 페이지 확인 |
| `GET /listings/{id}` | 본인 입력 조회 |
| `DELETE /listings/{id}` | 입력과 하위 분석 결과 삭제 |
| `POST /listings/{id}/analyses` | 기존 분석 호출 및 결과 저장 |
| `GET /analyses/{id}` | 저장 결과 조회 |
| `POST /extractions` | 이미지에서 확인용 항목 추출 |
| `GET /extractions/{id}` | 본인 추출 텍스트 조회 |
| `DELETE /extractions/{id}` | 추출 텍스트 삭제 |

HTTP 401=세션 필요, 404=본인 자료 없음, 413=업로드 초과, 422=요청 형식 확인, 502=외부 API 응답 실패, 503=데이터·설정 미연결입니다. 분석의 `INPUT_REVIEW_REQUIRED` 등은 HTTP 오류가 아닌 기존 분석 결과 상태입니다. 저장 API의 `validation.ok`는 정규화 통과 여부이며 최종 가격 판정 가능 여부가 아닙니다.

## 4. 주소·이미지 API

- 주소 검색: `KAKAO_REST_API_KEY` 환경변수 필요. 결과의 `b_code`를 사용하며 행정동 코드 `h_code`는 사용하지 않습니다. 건물 주소 후보일 뿐 호수·면적·임대료를 알아내지 않습니다.
- 이미지: `OPENAI_API_KEY`, `OPENAI_VISION_MODEL` 필요. 해당 계정에서 이미지 입력과 JSON Schema 출력을 지원하는 모델을 지정하세요. Chat Completions의 `json_schema` 출력을 사용합니다.
- 원본 캡처는 서버 DB에 저장하지 않으며 메타데이터 제거 후 외부 AI API로 전송합니다. 전화번호·임대인 이름 등은 업로드 전에 가리도록 화면에서 안내해야 합니다. 모델 추출 텍스트는 세션별 저장되며 삭제할 수 있습니다. 외부 제공자의 보관 정책은 별도로 확인해야 합니다.
- 이미지 형식 JPG/PNG/WebP, 정지 이미지, 8MB·1600만 화소 이하. 여러 매물/미기재 정보는 채우지 않습니다. 모든 추출값을 검토 대상으로 표시하고 층 문구는 기존 분류기로 교차 검사합니다.
- 외부 API 미설정 시 503. 이번 검증은 모의 외부 응답으로 진행했고 실제 키로 호출한 성공 검증은 하지 않았습니다.
- 공식 문서: [Kakao Local](https://developers.kakao.com/docs/ko/local/dev-guide), [OpenAI vision](https://developers.openai.com/api/docs/guides/images-vision), [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## 5. 회의 내용과 실제 구현 범위

| 내용 | 반영 |
| --- | --- |
| 아파트·오피스텔·연립다세대 등 | 기존 분석 함수 지원 범위를 그대로 사용. 구별 데이터 확보 필요 |
| 주소·동·호수 입력 | 저장 및 조회. 동일 호실 실거래 확인 기능 아님 |
| 캡처 자동입력 | 추출 API와 검토용 응답. 프론트 폼 반영은 프론트 담당 |
| 가격 범위·차이 금액/비율·근거 | 기존 결과를 그대로 저장·반환 |
| 관리비·옵션 | 별도 보관/전달. 시세 점수에 임의 반영하지 않음 |
| 동일 건물 우선 비교 | **미구현**. 현재 분석은 동 → 조건 완화 → 구 단위 탐색 |
| 연식·면적·층·주차·엘리베이터 유사도 % | **새로 만들지 않음**. 기존 confidence_details만 반환. 정확도 %로 표시 금지 |
| 전세사기 진단 | 후속 범위, 미구현 |

기존 자료에서 확인한 지원 자치구는 관악·광진·마포·동작·강서·노원입니다. 서울 전체 지원으로 표시하지 않습니다. 실제 데이터가 없는 구·유형은 비교 자료 부족 상태가 나올 수 있습니다.

## 6. 배포와 남은 작업

Docker 설정은 포함했지만 실제 배포는 하지 않았습니다. 루트에서 `docker build -f backend/Dockerfile -t rent-backend .` 후 컨테이너의 `/app/backend/data`를 영속 볼륨으로 연결하세요. 컨테이너 사용자가 해당 볼륨에 쓸 수 있어야 합니다. 정제 CSV도 같은 위치에 넣어야 합니다.

현재는 로컬/팀 내부 MVP용입니다. 사용자별 세션 토큰은 로그인 계정이 아니며 토큰을 잃으면 복구할 수 없습니다. 공개 서비스 전에는 계정 인증, 세션 만료, 업로드·AI 호출 속도/비용 제한, HTTPS, DB 백업·보관 정책을 추가해야 합니다. CORS는 인증 수단이 아닙니다. 프론트에 외부 API 키를 전달하지 않습니다.

### 3일 작업 순서

- 1일차: 분석 담당 정제 CSV 연결 → `/health` READY → 직접 입력·분석 확인.
- 2일차: 프론트와 등록/결과 연동 → 주소 검색 키 설정 → 캡처 추출·수정 흐름 확인.
- 3일차: 실제 동의받은 캡처/매물로 오류 확인 → 입력값·층·단위 대조 → 팀 내부 배포 및 백업.

## 7. 현재 검증·프론트 응답 예시

현재 진행 상태·담당별 선행 조건·미팅 초안은 [IMPLEMENTATION.md](IMPLEMENTATION.md)를 기준으로 합니다. 전달본의 과거 테스트 수를 현재 결과로 사용하지 않습니다.

[examples/api_responses.json](examples/api_responses.json)은 현재 API를 가상 신규 계약 40건으로 실행해 생성한 요청·등록 응답·분석 응답입니다. 운영 매물·정확도 근거가 아닙니다. COMPARED, INPUT_REVIEW_REQUIRED, REFERENCE_ONLY, INSUFFICIENT_DATA 및 422/503을 포함합니다. 새 요청에서는 파일의 UUID를 재사용하지 말고 등록 응답의 id를 사용하세요. 토큰은 포함하지 않았습니다.

| 표시 항목 | result 경로·단위 |
| --- | --- |
| 중간 50% 가격 범위 | prices_10k_krw.q25 ~ q75, 만원 |
| 중앙값·입력과 차액 | prices_10k_krw.median, rent_difference_10k_krw, 만원 |
| 차이율 | rent_difference_pct는 비율. 0.6 → 60%로 표시 |
| 조건·표본 수 | reference.conditions / relaxed_conditions / sample_count |
| 신뢰도·판단 보류 | confidence_grade / confidence_details / hold_reasons / reason_codes |
| 안내·확인 사항 | messages / warning_texts / input_issues / input_notes / errors |
| 비교 개별 거래 목록 | 현재 제공하지 않음. 통계나 예시로 목록을 만들어 표시하지 않음 |

입력 확인/자료 부족에서는 가격 범위·차액이 null일 수 있습니다. null은 0원이 아니며 그대로 미제공 상태로 표시합니다. OUT_OF_SCOPE도 표시해야 합니다. 참고용 결과는 가격 범위가 있어도 UNRATED를 유지합니다. percentile과 confidence_details를 가격 정확도나 사기 확률로 표현하지 않습니다.

프론트 연결 예(설명용):

```javascript
const base = 'http://127.0.0.1:8000';
async function call(path, method = 'GET', body, token) {
  const response = await fetch(base + path, {
    method,
    headers: {
      ...(body ? {'Content-Type': 'application/json'} : {}),
      ...(token ? {Authorization: `Bearer ${token}`} : {})
    },
    ...(body ? {body: JSON.stringify(body)} : {})
  });
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) throw {status: response.status, detail: data.detail};
  return data;
}
const {token} = await call('/sessions', 'POST');
// reviewedInput는 사용자가 실제로 검토/수정한 listing/options/confirmation.
const saved = await call('/listings', 'POST', reviewedInput, token);
// 확인이 안 된 초안은 validation.issues를 표시하고 새 입력으로 재등록.
const analysis = await call(`/listings/${saved.id}/analyses`, 'POST', undefined, token);
const persisted = await call(`/analyses/${analysis.id}`, 'GET', undefined, token);
```

토큰은 해당 사용자 브라우저에서만 보관하고 로그·URL·공유 예시에 넣지 않습니다. 401은 새 세션이 필요하며 기존 토큰을 잃으면 자료 복구가 안 됩니다. 404는 본인 자료 없음, 422는 입력 폼 수정, 502는 외부 오류 재시도/직접 입력, 503은 데이터/외부 설정 미연결입니다. 세션 삭제 후 이전 토큰으로 재요청하지 않습니다.

주소 검색 후보는 사용자 선택 후 district_code·legal_dong_code·dong을 함께 복사합니다. building_dong은 건물 동, dong은 법정동, unit_ho는 호수입니다. 코드 형식/자치구 불일치는 422입니다. 원본 이미지 업로드는 FormData의 file을 사용하고 Content-Type을 직접 지정하지 않습니다. 추출 응답의 fields는 초안이며 confirmation.user_confirmed를 자동으로 true로 설정하지 않습니다. 사용자가 확인한 뒤 새 /listings 요청을 보냅니다.

숫자 입력에 불리언은 허용하지 않습니다. 층·전체 층·건축연도는 정수 또는 null이며 소수부를 잘라 저장하지 않습니다. floor=0은 기존 계약대로 미확인입니다. 관리비는 0 이상 또는 null이며 가격 통계와 별개입니다.

## 8. 재현과 배포 점검

### 사진 초안·사용자 수정본 연결 (2026-10-19 구현)

`POST /listings` 최상위에 선택 필드 `source_extraction_id`(추출 응답 id), `previous_listing_id`(수정 전 매물 id)를 보낼 수 있습니다. 기존 `listing/options/confirmation`은 그대로 유지합니다. 연결 필드는 분석 입력에 전달하지 않습니다.

1. `POST /extractions` → 추출된 fields를 수정 폼에 채움. 원본 이미지는 저장하지 않음.
2. 초안을 보관할 때는 `source_extraction_id`와 `confirmation.user_confirmed=false`, `input_source=IMAGE_REVIEWED`로 매물 등록. 이 매물의 분석 요청은 INPUT_REVIEW_REQUIRED.
3. 사용자 수정·확인 후 새 매물을 등록하면서 `previous_listing_id`를 지정. 이전 매물에 살아 있는 추출 참조가 있으면 자동으로 이어받음. `user_confirmed=true`, `input_source=IMAGE_REVIEWED`, 실제 확인한 confirmed_fields를 전달.
4. 새 매물 id로 분석하고 저장 결과를 조회. 이전 입력과 분석은 덮어쓰지 않음.
5. 목록 조회는 같은 사용자 토큰으로만 가능. `limit` 1~50, `offset` 0이상, 응답 items/limit/offset/has_more.

매물 응답의 `links`에 두 참조를 반환하고 `confirmation_recorded_at`은 확인 표시를 포함해 서버에 등록한 시각입니다(미확인 초안은 null). 다른 세션/없는 참조는404, 추출 참조를 ADDRESS_MANUAL로 등록하면422. 확인 버튼은 프론트가 실제 사용자 동작으로 구현해야 하며 서버의 boolean 기록이 사람의 검토를 독립 인증하는 것은 아닙니다.

원본 추출을 삭제해도 이미 확인한 매물과 결과는 보존되고 추출 참조만 null로 바뀝니다. 이전 매물을 삭제해도 별도로 등록한 새 수정본은 남습니다. 각 매물 삭제 시 그 매물의 분석 결과는 삭제되고 세션 삭제 시 보관 자료 전체가 삭제됩니다. 기존 DB에는 연결 테이블만 추가하며 기존 입력·결과를 지우지 않습니다.

### 관리비 표시 원칙

공식2025 FILE과2026 Sheet 원본23열을 확인했으며 관리비·전기·수도·가스·인터넷·주차 비용 열이 없습니다. 종전 임대료는 이전 월세이며 관리비가 아닙니다. 이 자료만으로 관리비 포함 여부를 추정하지 않습니다.

- 사용자가 입력/확인한 관리비는 `options.maintenance_10k_krw`(만원)에 따로 보관합니다. 미기재는 null, 명확히0원일 때만0입니다.
- 가격 비교는 기존 월세 기준으로 유지합니다. 관리비를 월세에 더해서 실거래와 비교하지 않습니다. 관리비가 저렴/비쌈이라고 판정할 비교 근거도 없습니다.
- 화면 제안: 월세70만원 / 관리비10만원 / 확인된 합계80만원 / 전기·가스 등 추가 비용은 별도 확인. 합계 표시 UI는 프론트 연결 항목이며 현재 새 API 필드를 구현한 것은 아닙니다.
- 전기·가스·수도 포함 여부와 인터넷 상태는 기존 options 상태값을 사용하고 모르면 UNKNOWN으로 표시합니다. '인터넷 가능'을 비용 포함으로 바꾸지 않습니다. 월세/관리비 합쳐서만 적힌 광고는 임의로 분해하지 않고 별도 금액을 확인한 뒤 시세 분석합니다.

```bash
python -m pytest backend/tests -q -p no:cacheprovider
python -m backend.tests.export_examples
python -m backend.tests.smoke_server
```

두 보조 실행은 임시 가상 CSV·DB를 사용합니다. export_examples만 backend/examples/api_responses.json을 갱신합니다. smoke_server는 실제 127.0.0.1 임시 포트에서 데이터 READY/MISSING 서버를 각각 실행하고 종료합니다. 외부 API를 호출하지 않습니다.

현재 Windows 실행 검증의 주요 버전은 Python 3.12.10, FastAPI 0.146.0, Starlette 1.9.0, Pydantic 2.14.1, pandas 2.3.3, NumPy 2.5.4, httpx 0.28.1입니다. requirements는 기존 허용 범위를 유지했습니다. Docker는 이 PC에서 도구 부재로 빌드하지 못했고 외부 배포는 하지 않았습니다.

컨테이너의 /ready를 배포 대상의 readiness 경로로 연결하고 DB·정제 CSV는 영속 볼륨으로 보관합니다. 실거래 파일이 없으면 /health는 서버 생존 상태 200, /ready는 503입니다. CORS_ORIGINS에 실제 프론트 주소를 설정하고 HTTPS·자료 접근·백업/복원·운영 키를 배포 환경에서 검증해야 합니다. 현재 계정 인증·세션 만료·호출 비용 제한은 미구현이므로 팀 내부 MVP 범위로 구분합니다.
# 매물 전체 결과 연결 (2026-10-19)

전체 사용 순서: 세션 발급 → 주소 검색/직접 입력 또는 이미지 초안 추출 → 사용자 검토 → 매물 등록 → 기존 월세 분석 요청 → 관리비 근거 등록(선택) → 전체 결과 조회. 근거 자료가 없어도 월세 분석은 진행하며, 관리비 미입력을 0원으로 표시하지 않는다.

`GET /listings/{listing_id}/report`는 자신의 매물 전체를 한 응답으로 반환한다. 읽기 전용으로 새 분석이나 외부 AI 호출을 발생시키지 않는다. 수정 매물은 기존 방식으로 새 등록 후 새 ID로 분석한다.

| 결과 항목 | 내용 |
| --- | --- |
| property | 주소·동/호수·유형·면적·층 등 원입력, 확인 상태, 검증 결과, 이미지/이전 매물 연결 |
| rent | 마지막으로 저장한 분석 결과 원문, 분석 ID/시간. 가격 범위·차액·차이율·표본 수·신뢰도·상태는 기존 계약 유지 |
| maintenance | 입력 관리비와 해당 매물에 연결한 출처별 대조 자료. 지역 평균 아님 |
| options | 관리비 총액을 제외한 기존 옵션 항목. 누락을 무료/제공으로 채우지 않음 |
| monthly_cost | 확인된 입력 월세+관리비 소계. 공과금 등 추가 비용이 빠질 수 있어 총 생활비로 표현하지 않음 |
| workflow | 현재 데이터 연결 상태와 필요한 다음 동작 |

분석 전 `rent.state=NOT_ANALYZED`, 관리비 근거가 없으면 `maintenance.state=NO_EVIDENCE`. 사용자 미확인·잘못된 입력·금액 미상은 소계를 보류한다. 관리비 0원은 유효한 명시 입력이다. 분석 통계만 제공되는 현재 분석기의 한계를 숨기지 않도록 `comparable_transactions=null`, `comparable_transactions_state=NOT_PROVIDED_BY_ANALYSIS`를 제공한다.

관리비 자료는 `evidence_limit`(기본20, 최대50), `evidence_offset`으로 페이징하며 `total/has_more`를 확인한다. `REVIEW_MAINTENANCE_EVIDENCE`는 조회한 페이지의 검토 필요 자료를 뜻하며 전체 페이지 검증 완료를 의미하지 않는다. `workflow.next_actions`는 REVIEW_LISTING/RUN_RENT_ANALYSIS/CONNECT_RENT_DATA/REVIEW_RENT_RESULT/ADD_MAINTENANCE_AMOUNT/ADD_MAINTENANCE_EVIDENCE/REVIEW_MAINTENANCE_EVIDENCE 중 필요한 동작을 반환한다. 프론트는 기존 분석 라벨·보류 사유를 함께 표시해야 한다.

# 관리비 자료 대조 (2026-10-19)

월세 분석과 별도 기능이다. 지역 평균·바가지 판정이 아니라 입력한 관리비와 출처에 적힌 금액을 대조한다. 광고는 실제 청구서가 아니다. 원본 사진·연락처를 저장하지 않는다. URL은 기록만 하며 서버가 임의 URL에 접속하지 않는다.

- `GET /maintenance/reference-cases`: 이 PC에 확보한 공개 사례. `backend/data/maintenance_public_cases.json`이 없거나 잘못되면 503. 공개 사례 파일은 Git 제외이므로 다른 PC/배포에는 별도 전달·검토가 필요하다.
- `POST /listings/{listing_id}/maintenance-evidence`: 기존 세션으로 자신의 매물에 자료와 대조 결과를 저장한다.
- `GET /maintenance-evidence?limit=20&offset=0`: 자신의 자료 목록.
- `GET /maintenance-evidence/{id}`, `DELETE /maintenance-evidence/{id}`: 조회·삭제. 매물/세션 삭제 시 함께 삭제된다.

등록 예시 (통제 표본, 실제 청구서 아님):

```json
{
  "source_type": "ADVERTISEMENT",
  "source_title": "매물 광고",
  "source_url": "https://example.org/listing/1",
  "observed_on": "2026-10-19",
  "amount_10k_krw": 5,
  "period": "MONTH",
  "basis": "UNKNOWN",
  "applies_to": "SAME_UNIT",
  "user_confirmed": true,
  "items": {"WATER": "INCLUDED", "INTERNET": "INCLUDED"}
}
```

`source_type`: ADVERTISEMENT/PUBLIC_NOTICE/MANAGER_STATEMENT/BILL. 출처 종류는 제출자가 선택하며 진위 인증을 의미하지 않는다. `period`: MONTH/YEAR/UNKNOWN, `basis`: FIXED/ACTUAL/ESTIMATE/UNKNOWN. `applies_to`: SAME_UNIT/SAME_BUILDING/OTHER/UNKNOWN. 건물만 같고 호실이 다르면 직접 차액 계산을 보류한다. 주소/호실 자동 동일성 검증은 미구현이며 `SAME_UNIT`도 사용자의 확인 내용이다.

`items`는 COMMON/WATER/ELECTRICITY/GAS/INTERNET/TV/PARKING별 INCLUDED/EXCLUDED/UNKNOWN. 생략은 UNKNOWN이며 무료·별도로 추정하지 않는다. `billing_month`는 선택적인 YYYY-MM이다. 확인하지 않은 이미지 결과는 `user_confirmed:false`로 저장하고 검토 후 새 자료로 등록한다. 이미지 추출 결과를 관리비 자료에 자동 변환하는 프론트 연결은 미구현이다.

응답 `comparison.status`는 AMOUNT_MATCH(숫자 일치), AMOUNT_DIFFERENCE(차액 있음), NEEDS_REVIEW(확인 필요). 입력 매물과 근거 자료가 모두 확인되고 같은 호실·월 금액·양쪽 금액이 있을 때만 `difference_10k_krw = 입력 - 근거`를 제공한다. 0은 미기재와 다르다. 포함 항목의 동일성·고지서 진위·해당 월의 적정성을 인증하지 않으며 `unknown_items`, 출처/확인 날짜/부과 기준을 함께 표시해야 한다. 여러 근거 간 자동 합산·시세 모델·정기 광고 수집은 구현 범위 밖이다.
