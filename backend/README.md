## 2026-10-22 최신 보완 — 미체크 참고값·가운데 값

기준 CSV는 팀 저장소에 확보되어 있습니다(1,012행). CSV 미확보라는 과거 안내는 현재 상태가 아닙니다. 기존 분석 함수 month_ref를 같은 조건으로 호출해 미체크 전기·수도·가스·인터넷 참고값도 연결했습니다. 광고 포함 여부와 분석 원본은 바꾸지 않습니다. 기타·조건 부족 항목은 null입니다.

관리비 대표금액은 미팅 확정대로 (최소+최대)÷2입니다. 월세 실거래 중앙값은 변경하지 않습니다. 항목은 reference_midpoint_krw, 묶음은 reference_midpoint_total_krw입니다. 자료 없는 항목이 있으면 묶음 합계는 null입니다. 대표값은 원 단위이며 0.5원도 보존하므로 프론트에서 임의 반올림하지 않습니다.

정식 저장 경로 POST /listings/{id}/maintenance-references → GET /maintenance-references/{id} → 보고서의 maintenance_reference_groups를 사용합니다. 구형 단수 preview 경로와 혼동하지 마세요. 기존 저장 결과는 자동 갱신하지 않으며 새 계산 요청으로 새 결과를 저장합니다. 추가 조건을 묻는 새 화면을 요구하지 않습니다. 이미 있는 조건이 부족하면 해당 값만 null로 남깁니다.

검증: 실제 기준 CSV 및 격리 DB를 사용한 전체 243개 통과, 경고 4개. 집 서버 적용·오늘 DB 행 수·실제 프론트 통합은 미확인입니다. 이는 실제 고지서 정확도 검증과 다릅니다.

프론트 요청: 체크 5항목+총액 입력을 유지하고, 체크/미체크 두 묶음에서 대표금액·누락 항목을 표시해주세요. 접속키는 별도 전달합니다.
분석 요청: 현재 호출하는 month_ref를 대체/보장하는 정식 전체항목 연결 함수를 정리해주세요. 기타 참고 자료가 있으면 출처와 함께 전달해주시고 없으면 null로 유지합니다. 강서2·송파1 실제값 대비 결과·오차도 공유 부탁드립니다. CSV 재전달이나 대표값 결정 요청은 아닙니다.

집 인계: 최신 코드 pull → DB 백업 → 분석 CSV 경로·관리비 활성화 설정 확인 → 서버 재시작 → 새 참고값 계산 요청 → 저장·재조회와 재시작 유지 확인 → 프론트 테스트 안내. 기존 원본·DB·키는 보존합니다.

---

> **결과 표시 응답 추가(2026-10-22):** report.rent.presentation에서 차액·퍼센트·빨강/파랑/중립·상태 문구를 제공합니다. 참고용·자치구 확대는 방향 판정 없이 표시하고 원본 분석은 유지합니다. [연결 규격과 팀 최신 확인](FRONTEND_RESULT_DISPLAY.md).

> **매장 재확인(2026-10-22):** 개인·팀 최신 main 동기화, 실제 기준 CSV 포함 로컬 전체 시험 226 통과·경고 4개. 집 Tailscale 온라인이나 SSH 22/22222 연결 불가로 오늘 집 DB/서버 재검증은 미완료. 미체크 참고값의 분석 반환 누락도 확인. [오늘 실제 결과](SHOP_RESULT_20261022.md)가 아래 과거 설치 중·CSV 미확보·PR OPEN 기록보다 우선합니다.

> **2026-10-22 갱신:** 새 분석 PR에서 기준 CSV를 확보했습니다. 관리비 참고값 계산·별도 DB 저장·재조회 API와 격리 MySQL 재시작 시험을 추가했으며 운영 계산은 보류 상태입니다. [연결 규격](MACHINE_REFERENCE_API.md) · [다음 미팅 공유안](NEXT_MEETING_SHARE_20261022.md). 이전 CSV 미확보 기록보다 이 안내를 우선합니다. 집 OpenSSH 설치·설정 검증도 완료했으며 매장 공개키와 실제 접속 시험은 남아 있습니다.

> **집 서버 실제 적용 완료(2026-10-21):** 월세구멍·5항목 체크+총액 저장·월세 비교·재시작 유지·기존 7항목 원본 보존을 확인했습니다. 기준 CSV 확보·로컬 참고값 연결 검증 완료. 실제 3건 정확도 검증과 집 운영 최신 적용은 별도 확인이 필요합니다. [실제 결과·행 수·제한·프론트 전달 초안](HOME_PC_RESULT_20261021.md). 아래 이전 미완료 기록보다 이 결과를 우선합니다.

> **10/21 미팅 확정 — 월세구멍:** 슬로건은 “마음에 든 집, 놓친 건 없을까?”. 관리비는 모든 주택 유형에 수도세·전기세·가스비·인터넷·기타 관리비 5항목으로 통일합니다. 청소·공용은 기타의 설명으로 보존하며 별도 항목을 추가하지 않습니다. 고객은 체크박스+총액만 입력합니다. 이전 미확정 안내보다 이 결정이 우선합니다.

> **최신 입력·결과 확정(2026-10-21):** 고객은 5개 항목 체크 + 선택된 항목의 관리비 총액 한 칸만 입력합니다. 결과는 체크/미체크 항목의 분석 참고비용을 분리합니다. [새 연결 규격](CHECKBOX_MAINTENANCE.md)이 이전 상세금액 입력 안내보다 우선합니다. 실제 분석값 연결·집 배포는 미완료이며 지원 범위는 별도 논의 중입니다.

> **최신 5항목 규격(2026-10-21):** 현재 구현은 전기·수도·가스·인터넷·기타 관리비 5항목입니다. 신규 저장은 총액 1행+항목 5행, 과거 7행은 삭제하지 않고 호환 조회합니다. [프론트 필드·기존 자료 처리](ADVERTISED_COSTS.md). 아래 과거 7항목 설명보다 이 규격이 우선하며, 집 실행 서버 적용은 별도 확인해야 합니다.

# 팀 백엔드 실행·연결 안내

2026-10-20 기준. 현재 실행 안내는 이 문서, 프론트 규격은 [FRONTEND_HANDOFF.md](FRONTEND_HANDOFF.md)를 기준으로 합니다.

## 현재 지원 범위

| 기능 | 상태 |
| --- | --- |
| 매물 입력·분석 결과 저장 | MySQL 8.x에 영속 저장, 세션별 조회·삭제 |
| 월세 비교 | 팀 서버는 v2, 같은 법정동부터 조건 완화·같은 구 비교 |
| 광고 관리비 입력 | 총액·포함 여부·명시 금액·설명 저장 및 표시 |
| 관리비 적정성·공과금 계산 | 팀 공유 서버에서 보류, ON_HOLD |
| 같은 건물 우선 비교 | 비활성화 |
| 주소 검색·이미지 추출 | 별도 외부 API 설정 필요, 현재 실연동 검증과 구분 |
| 프론트 화면 | 원본은 오프라인 시안. 실제 화면 통합 검증은 별도 |

분석은 `machine/` 원본을 직접 불러옵니다. 분석 파일을 저장소 루트로 복사하거나 `backend/backend/`를 만들지 않습니다.

## 새 개발 환경 실행

저장소 루트에서 실행합니다. Python 의존성을 설치하고 `backend/.env.example`을 참고해 Git 제외된 `backend/.env`에 설정합니다.

```shell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --env-file backend/.env --host 127.0.0.1 --port 8000
```

실행 전에 MySQL 8.x DB와 스키마를 준비해야 합니다. [MYSQL.md](MYSQL.md)의 초기화·계정 권한·기존 데이터 이전 절차와 [MAINTENANCE_DB.md](MAINTENANCE_DB.md)의 관리비 테이블 후속 적용을 따릅니다. `DATABASE_URL`이 없으면 새 SQLite로 자동 대체하지 않습니다. SQLite는 명시적 레거시·테스트 용도입니다.

| 환경변수 | 용도 |
| --- | --- |
| DATABASE_URL | 비공개 MySQL 연결 문자열 |
| DB_AUTO_INIT=false | 스키마 관리 계정으로 초기화한 뒤 일반 실행에서 사용 |
| RENT_CLEAN_CSV | 별도 준비한 정제 실거래 CSV 경로 |
| ANALYSIS_ENGINE=v2, V2_ENABLED=true | 현재 팀 서버 분석 엔진; 예시 파일 기본값 v1과 구분 |
| SAME_BUILDING_ENABLED=false | 같은 건물 비교 비활성화 |
| MAINTENANCE_ENABLED=false | 팀 공유 서버의 관리비 계산 보류 |
| CORS_ORIGINS | 실제 프론트 origin을 정확히 지정 |

비밀번호·접속키·CSV·DB·SQL 백업은 Git에 올리지 않습니다. 기존 DB에 스키마를 적용하기 전 백업하고, 입력·분석 원본을 예시 데이터로 덮어쓰지 않습니다.

## 현재 PC의 팀 공유 서버

wlsdu PC의 비공개 runtime은 `C:/Users/wlsdu/AppData/Local/YeardreamRentBackend`입니다. 최신 주소는 `접속주소.txt` 또는 `connection.json`, 접속키는 `team-access.key`, 시작·종료는 `server-start.cmd`·`server-stop.cmd`를 사용합니다. 키는 별도 신뢰할 수 있는 경로로 전달합니다.

임시 HTTPS 주소는 재시작 시 바뀔 수 있습니다. PC가 켜져 있고 절전 상태가 아니어야 합니다. Git pull은 MySQL·실거래 CSV·비밀 설정을 설치하지 않습니다. 이전 jhj12 PC 경로와 옛 임시 주소를 사용하지 마세요. 상세: [TEAM_SERVER.md](TEAM_SERVER.md).

## 프론트 API 연결

`POST /sessions` → `GET /capabilities`, `GET /locations` → `POST /listings` → `POST /listings/{id}/analyses` → `GET /listings/{id}/report`.

모든 요청에 `X-Team-Key`, 세션 생성 이후 개인 데이터 요청에 `Authorization: Bearer ...`를 보냅니다. `property.input`, `rent.result`, `advertised_costs`를 기존 계약대로 사용합니다. 접속키 없이 주소만 브라우저에서 열면 401일 수 있습니다.

- [프론트 연결·오류 처리](FRONTEND_HANDOFF.md), [실제 연결 모듈](frontend_api_example.mjs)
- [광고 관리비 입력 계약](ADVERTISED_COSTS.md), [관리비 DB 구조](MAINTENANCE_DB.md)
- [재시도 중복 방지](RETRY_REQUESTS.md), [v2 연동](ANALYSIS_V2.md)
- [현재 예시 응답](examples/api_responses.json) — 합성 사례이며 실제 조회 결과가 아닙니다.

`backend_briefing.*`와 루트 전달 JSON은 과거 기록입니다. 공과금 참고 견적 예시가 있어도 현재 팀 서버의 기능 활성화를 뜻하지 않습니다.

## 검증과 한계

2026-10-20 개인 저장소 410902a에서 실제 MySQL 전체 검사 188개와 프론트 클라이언트 검사 2개를 통과했습니다. CI는 MySQL 8.0·8.4 및 컨테이너 smoke를 통과했습니다. 이후 공개 HTTPS에서 등록·분석·보고서·CORS·세션 격리·관리비 7항목 저장을 재확인했습니다. 검사 데이터는 정리했습니다.

앱·팀 DB SQL 백업을 만들었습니다. 이번 최신 백업의 복원 검증, 실제 프론트 화면 전체 흐름, 상시 운영 배포는 미완료입니다. 요청 진단 기능은 응답의 `X-Request-ID`와 서버의 API 경로 템플릿·HTTP 상태·처리 시간을 연결합니다. CORS 응답에서도 해당 헤더를 읽을 수 있습니다. 키·토큰·본문·쿼리·실제 매물 ID는 진단 로그에 기록하지 않습니다. 변경 전부터 실행 중인 서버에는 다음 재시작 후 적용됩니다. 오류를 전달할 때 요청 ID·프론트 실행 주소·API 경로·HTTP 상태·응답 메시지를 제공하고 키와 토큰은 제외해주세요.

```shell
python -m pytest backend/tests -q --require-mysql
node --test backend/tests/frontend_client.test.mjs
```

MySQL 검사는 실사용 DB가 아닌 전용 `MYSQL_TEST_DATABASE_URL`을 설정한 뒤 실행합니다. 운영 준비는 [DEPLOYMENT.md](DEPLOYMENT.md), 이전 구현 설명은 [보존 기록](IMPLEMENTATION_HISTORY_20261020.md)을 참고합니다. 보존 기록의 실행법·PC 경로·검사 수보다 현재 안내가 우선합니다.


최근 재검토: [2026-10-21 팀 ZIP 비교·후속 개발](ZIP_REVIEW_20261021.md). 프론트 연결 모듈은 요청 시간 제한과 오류 요청 ID를 지원하며 Node 검사 5개를 통과했습니다.
