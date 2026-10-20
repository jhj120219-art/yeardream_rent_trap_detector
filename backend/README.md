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

앱·팀 DB SQL 백업을 만들었습니다. 이번 최신 백업의 복원 검증, 실제 프론트 화면 전체 흐름, 상시 운영 배포는 미완료입니다. 현재 서버는 요청 접근 로그를 남기지 않으므로 기존 로그만으로 프론트의 개별 실패 요청을 추적할 수 없습니다. 오류를 전달할 때 프론트 실행 주소·API 경로·HTTP 상태·응답 메시지를 제공하고 키와 토큰은 제외해주세요.

```shell
python -m pytest backend/tests -q --require-mysql
node --test backend/tests/frontend_client.test.mjs
```

MySQL 검사는 실사용 DB가 아닌 전용 `MYSQL_TEST_DATABASE_URL`을 설정한 뒤 실행합니다. 운영 준비는 [DEPLOYMENT.md](DEPLOYMENT.md), 이전 구현 설명은 [보존 기록](IMPLEMENTATION_HISTORY_20261020.md)을 참고합니다. 보존 기록의 실행법·PC 경로·검사 수보다 현재 안내가 우선합니다.
