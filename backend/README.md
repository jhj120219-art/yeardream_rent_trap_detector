# 월세 비교 백엔드 — 기존 분석 코드 연동

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

```bash
python -m pytest backend/tests -q -p no:cacheprovider
python -m backend.tests.export_examples
python -m backend.tests.smoke_server
```

두 보조 실행은 임시 가상 CSV·DB를 사용합니다. export_examples만 backend/examples/api_responses.json을 갱신합니다. smoke_server는 실제 127.0.0.1 임시 포트에서 데이터 READY/MISSING 서버를 각각 실행하고 종료합니다. 외부 API를 호출하지 않습니다.

현재 Windows 실행 검증의 주요 버전은 Python 3.12.10, FastAPI 0.146.0, Starlette 1.9.0, Pydantic 2.14.1, pandas 2.3.3, NumPy 2.5.4, httpx 0.28.1입니다. requirements는 기존 허용 범위를 유지했습니다. Docker는 이 PC에서 도구 부재로 빌드하지 못했고 외부 배포는 하지 않았습니다.

컨테이너의 /ready를 배포 대상의 readiness 경로로 연결하고 DB·정제 CSV는 영속 볼륨으로 보관합니다. 실거래 파일이 없으면 /health는 서버 생존 상태 200, /ready는 503입니다. CORS_ORIGINS에 실제 프론트 주소를 설정하고 HTTPS·자료 접근·백업/복원·운영 키를 배포 환경에서 검증해야 합니다. 현재 계정 인증·세션 만료·호출 비용 제한은 미구현이므로 팀 내부 MVP 범위로 구분합니다.
