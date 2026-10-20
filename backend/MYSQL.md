# MySQL 8.x 전환 및 영속성 검증

## 2026-10-20 현재 PC 연결 결과

개인 main을 `02f95e6`에서 `ec03e69`까지 fast-forward pull했다. 바탕화면 `desktop_git_setup.zip`은 관리 대상 80개 파일이 이전 `02f95e6`과 모두 같았다(CRLF/LF 차이 정규화). 최신 코드에 ZIP을 덮어쓰지 않았다. 정제 CSV와 기존 SQLite도 이 PC와 SHA-256이 같아 복사하지 않았다. ZIP SHA-256은 `a09071172b0b17710afd2da01206edba2c7fbd897a2da38981e4bed6783fe1ad`.

**코드는 pull로 충분하지만 PC 환경과 개인 데이터는 Git에 없다.** 이 PC에 MySQL 드라이버·환경파일 라이브러리를 설치하고 공식 MySQL 8.4.11 Windows ZIP을 준비했다. 공식 MD5 `2e833921898a9a030ea6bfe81bd811bc`로 다운로드 무결성을 대조했다. 저장 위치는 저장소·OneDrive 밖의 사용자별 보호 폴더이며 사용자 본인과 SYSTEM만 접근하도록 설정했다. 시스템 서비스·PATH·방화벽 인바운드를 변경하지 않았다.

- MySQL은 `127.0.0.1:3307`에만 바인딩, MySQL X 포트 비활성화. `rent_app`, `rent_team`, `rent_test`를 분리했다. 앱·팀 계정에는 해당 DB의 SELECT/INSERT/DELETE만 부여하고 스키마 초기화는 별도 관리자 연결로 수행했다. DB 비밀번호와 환경 파일은 보호 폴더에만 저장하며 출력하거나 Git에 올리지 않았다.
- 기존 앱이 실행 중이지 않음을 확인한 후 SQLite를 읽기 전용으로 백업하고 새 MySQL에 이전·전체 값 대조했다. 원본 해시도 그대로 유지했다. 이전 시 양쪽 원본의 sessions/objects/object_links는 모두 0건이었다. 실제 사용자 자료를 복원했다고 보고하지 않는다.
- 실제 MySQL을 사용한 전체 테스트 **152 passed, 0 skipped**, Starlette/httpx 안내 1건. 합성 입력·분석 저장 후 독립 API 프로세스 재시작 조회와 마이그레이션·롤백 포함. 과거 집 PC/CI 통과 수를 재사용한 결과가 아니다.
- 추가로 로컬 MySQL 서버 자체 정상 종료→재시작 후 같은 토큰·객체 값 보존, mysqldump 백업→별도 검사 DB 복원→세 테이블 전체 행 값 일치까지 확인했다. 검사 세션·검사 DB는 정리했다. 이는 이 PC의 로컬 검사이며 운영 장애 전체 복구 검증이 아니다.
- 공유 HTTPS API도 MySQL 팀 DB에 연결했다. 키 없는 접근 차단, 세션별 격리, 실거래 READY, 가상 매물 분석 COMPARED, 보고서 관리비 ON_HOLD, 조회·삭제를 확인했다. 프론트 담당 PC의 화면 통합은 아직 확인하지 않았다. 현재 주소는 보호 runtime의 `접속주소.txt`를 기준으로 전달한다. 이전 보고서의 임시 URL은 재시작 후 사용하지 않는다.

### 이 PC 시작·종료·백업

`backend/scripts/local_mysql.py`는 이미 준비된 비공개 runtime을 관리한다. 설치 메타데이터·바이너리 경로와 실제 DB 데이터 경로를 확인해 다른 MySQL 인스턴스를 관리하지 않는다. `start`, `status`, `stop`, `backup` 동작을 제공한다. 저장소 밖 `deliverables/team_server`의 기존 시작·종료 버튼도 MySQL용으로 갱신했다. PC 부팅 시 자동 실행되도록 등록하지는 않았다.

```powershell
# runtime은 이 PC에서 준비한 보호 폴더로 지정한다. 비밀번호를 명령 인수에 넣지 않는다.
python -m backend.scripts.local_mysql start --runtime C:/private/YeardreamRentMySQL
python -m backend.scripts.team_server --runtime C:/private/YeardreamRentBackend --env-file C:/private/YeardreamRentMySQL/team.env
python -m backend.scripts.local_mysql backup --runtime C:/private/YeardreamRentMySQL
# API를 먼저 정상 종료한 다음 DB를 중지한다.
python -m backend.scripts.local_mysql stop --runtime C:/private/YeardreamRentMySQL
```

백업은 `rent_app`, `rent_team` 각각 single-transaction SQL 파일로 저장한다. 비밀번호는 일시적인 보호 client 파일로 전달하고 실행 후 삭제한다. 백업 파일은 원본과 같은 디스크에 있으므로 외부 백업은 별도다. MySQL 모드에서는 이전 SQLite 24시간 백업을 실행하지 않으며, 현재 백업은 명시적 실행·종료 버튼에서 수행한다. 주기적 MySQL 백업 자동화·상시 운영 배포·프론트 화면 통합은 별도 남은 항목이다.

이 PC의 정제 CSV와 DB는 준비됐지만 새 PC에서는 원본/정제 자료·비밀 설정·MySQL 설치가 따로 필요하다. `.venv`나 DB 폴더 전체를 ZIP에서 덮어쓰는 방식은 사용하지 않는다.

> **최신 검증 결과:** 2026-10-19 개인 GitHub CI에서 실제 MySQL 8.0·8.4 환경 각각 **140 passed, 0 skipped**. 아래 이전 실행의 “MySQL 미검증”은 후속 CI로 해소했다. 운영 DB 이전·운영 서버 배포는 수행하지 않았다.

## 설정

신규 서버는 `DATABASE_URL`이 필요하다. 설정이 없으면 임의의 빈 SQLite DB로 시작하지 않는다. `mysql://`와 `mysql+pymysql://`를 지원한다. 명시적 `BACKEND_DB_PATH`는 기존 SQLite/테스트용이며 두 값이 있으면 DATABASE_URL이 우선한다. MySQL 접속 실패 시 SQLite로 대체하지 않는다.

저장소 루트에서:

```powershell
python -m pip install -r backend/requirements-dev.txt
# backend/.env.example을 backend/.env로 복사하고 실제 비밀정보를 로컬에서 입력한다.
# DATABASE_URL=mysql+pymysql://rent_app:URL_ENCODED_PASSWORD@127.0.0.1:3306/rent_app
python -m uvicorn backend.app.main:app --env-file backend/.env --host 127.0.0.1 --port 8000
```

비밀번호의 @, /, %, # 등은 URL 인코딩한다. 원격 TLS 연결은 URL에 `?ssl_ca=인코딩된_CA_파일경로`를 추가한다(인증서·호스트 검증 활성화). URL과 비밀번호를 소스·공개 프론트 환경변수·로그에 기록하지 않는다. `.env`, 변형 환경 파일, SQLite 및 SQL 덤프는 Git에서 제외한다. 예시 파일에는 실제 비밀정보를 넣지 않는다.

이미 존재하는 MySQL 8.x DB를 사용하거나, Docker가 설치된 개발 PC에서는 private backend/.env의 MYSQL_PASSWORD / MYSQL_ROOT_PASSWORD를 서로 다른 비밀번호로 채운 후 다음을 실행한다. DATABASE_URL에도 같은 앱 계정 비밀번호를 URL 인코딩해 지정한다.

```powershell
docker compose --env-file backend/.env -f backend/compose.mysql.yml up -d --wait
```

DB명과 앱 사용자는 rent_app이며 포트는 로컬에만 바인딩된다. named volume에 데이터가 남는다. 서버를 중지할 때 `down`은 가능하지만 데이터를 보존하려면 `down -v`를 사용하지 않는다. 기존 서비스/3306 포트가 있다면 새 인스턴스를 중복 실행하지 않는다. 스키마 초기화에는 CREATE 권한, 요청 처리에는 SELECT/INSERT/DELETE 권한이 필요하다. 테이블은 InnoDB, utf8mb4, 대소문자를 구분하는 collation을 사용한다. 이 초기화는 새로운 테이블 생성용이며 이미 변형된 MySQL 테이블을 자동 보정하는 스키마 업그레이드 도구는 아니다.

## 기존 SQLite 데이터 이전

실제 기존 DB를 먼저 찾는다. Git에는 개인 DB가 없으므로 clone만으로 기존 사용자 데이터가 복구되지 않는다. `backend/data/app.sqlite3`, 팀 runtime/team.sqlite3, 기존 BACKEND_DB_PATH를 확인하고 세션 토큰도 그대로 보관한다. 토큰 자체는 DB에 없고 해시만 저장된다.

1. 원본 SQLite와 대상 MySQL을 사용하는 앱을 모두 중지한다. 이전 중 쓰기와 다른 마이그레이션 실행을 금지한다.
2. 대상은 새 빈 MySQL DB로 준비한다. 이미 자료가 있으면 도구가 거부한다. 병합/덮어쓰기하지 않는다.
3. 현재 프로세스의 DATABASE_URL을 대상 MySQL로 설정한다. `.env`는 이 명령에서 자동 로드하지 않는다.
4. 저장소 밖의 보호된 새 백업 파일 경로로 실행한다.

```powershell
python -m backend.scripts.migrate_mysql --source C:/private/app.sqlite3 --backup C:/private/backups/pre-mysql-001.sqlite3 --offline-confirmed
```

SQLite backup API가 WAL의 커밋 내용까지 스냅샷으로 보존하고 무결성·외래키를 확인한다. 원본은 read-only로 열며 백업 파일이 이미 있으면 거부한다. sessions → 부모 우선 objects → object_links 순서로 ID·세션 해시·원본 JSON 문자열·시간·소유자·분석 및 링크를 그대로 복사한다. 대상 INSERT와 전체 행 값 대조는 단일 트랜잭션으로 수행하며 실패 시 데이터 INSERT를 롤백한다. MySQL DDL은 별도 커밋이므로 실패해도 빈 테이블은 남을 수 있다. 소스 원본과 백업은 삭제하지 않는다.

5. 같은 세션 토큰으로 기존 매물·분석 조회를 확인한 뒤 프론트 API 연결을 재개한다. 전환 후 새 데이터가 생겼다면 SQLite로 단순 되돌릴 경우 새 데이터가 누락되므로 양쪽 앱을 멈추고 별도로 대조한다.

MySQL의 지속 백업은 mysqldump/운영 DB 백업으로 별도 구성하고 복구 시험을 한다. 팀 서버 도구는 MySQL에서 SQLite 백업을 실행하지 않는다. named volume은 백업이 아니다.

## 저장 범위와 API 호환성

- `POST /listings`: 원본 입력, 검증 결과, 확인 시각, 연결 ID를 저장한다. 등록 자체로 월세 분석을 만들지 않는다.
- `POST /listings/{id}/analyses`: 분석 실행 후 별도의 analysis 객체로 결과 스냅샷을 커밋한다. 자료 부족·입력 재확인 결과도 기존 계약대로 저장한다. 실거래 데이터 미연결 503에서는 분석 객체를 만들지 않는다.
- `GET /listings/{id}`, `GET /analyses/{id}`, `GET /listings/{id}/report`: 저장 자료를 조회한다. report.rent는 마지막 저장 분석이며 GET으로 새 분석을 생성하지 않는다.
- Bearer 세션, ID, v1.1 입력·응답·상태 코드, 소유자 격리, 삭제 cascade는 유지한다. 프론트와 원본 분석 코드를 수정하지 않는다.
- 이미지 원본과 파일명은 저장하지 않는다. 추출된 구조화 결과는 기존처럼 저장한다. 실거래 비교 CSV는 별도 입력이며 이번 전환의 세 테이블에 자동 수집·적재하지 않는다.

## 검증 명령

```powershell
python -m pytest backend/tests -q
# 실제 MySQL 테스트 전용 빈 DB의 URL을 MYSQL_TEST_DATABASE_URL에 설정 후:
python -m pytest backend/tests/test_mysql_persistence.py -q
```

일반 회귀 테스트는 운영 DATABASE_URL을 제거하고 SQLite 합성 표본을 사용한다. MySQL 통합 테스트만 MYSQL_TEST_DATABASE_URL을 사용한다. 운영 DB를 지정하지 않는다. 테스트는 독립 uvicorn 프로세스에서 입력 → API 재조회 → 직접 DB 행 확인 → 분석 저장 → 프로세스 종료 → 새 프로세스에서 동일 토큰으로 매물·분석 재조회를 수행한다. 별도 마이그레이션 테스트는 토큰·한글/이모지 payload·부모/링크·전체 값 보존, 비어 있지 않은 대상 거부를 검사한다. 테스트 자료는 성공 후 세션 단위로 삭제한다.

MYSQL_TEST_DATABASE_URL이 없으면 실제 MySQL 테스트는 skip되며 MySQL 통합 검증 완료를 의미하지 않는다. mock 드라이버 테스트는 파라미터 변환과 commit/rollback만 검증한다. Windows sandbox에서 루프백/스레드가 막히면 일반 로컬 터미널에서 실행한다.

근거: [MySQL 외래키 문서](https://dev.mysql.com/doc/refman/8.0/en/create-table-foreign-keys.html), [PyMySQL 연결 문서](https://pymysql.readthedocs.io/en/latest/modules/connections.html).

## 이번 실행 결과 — 2026-10-19 (KST)

- 빈 현재 작업 폴더에서 개인 origin `https://github.com/jhj120219-art/yeardream_rent_trap_detector.git`을 clone했다. 시작 main은 `02f95e6`, 미커밋 변경이 없었고 저장소/확인한 상위 경로에 AGENTS.md가 없었다. 팀 원본 ZIP은 Downloads에 존재하지만 이번 DB 전환에서는 통합하지 않았다.
- `python -m pytest backend/tests -q --basetemp=backend/data/pytest-final-1`: **134 passed, 3 skipped**, 9.62초. 설치된 Starlette/httpx 조합의 deprecation 경고 1건. 테스트는 Windows 일반 로컬 권한으로 실행했다. MySQL 드라이버는 Git 제외 `backend/.venv/vendor`에 설치하고 해당 경로를 PYTHONPATH에 추가했다.
- SQLite 합성 표본으로 HTTP 입력 → 조회 → 직접 DB 행 → 분석 저장 → 서버 프로세스 종료 → 새 프로세스에서 동일 토큰으로 매물/분석 조회를 확인했다. 분석 전 report.rent.analysis_id는 null이다.
- 마이그레이션의 SQLite 백업, 데이터/토큰/링크 일치, 대상 비어 있지 않음 거부, 잘못된 링크로 실패할 때 전체 INSERT 롤백을 확인했다. MySQL 어댑터의 placeholder·commit·rollback은 mock으로 확인했다.
- **실제 MySQL 통합 검증 미완료**: DATABASE_URL 및 MYSQL_TEST_DATABASE_URL이 없고 mysql/docker 실행 도구도 발견되지 않았다. 실제 MySQL HTTP 재시작, SQLite→MySQL 이전, MySQL 롤백 테스트 3건은 skip했다. Compose 실행·실제 MySQL DDL·인증·외래키 동작·운영 데이터 이전을 완료했다고 볼 수 없다.
- clone된 저장소에는 기존 개인 DB가 없었다. 기존 운영 데이터는 수정·삭제·이전하지 않았다. 별도 PC/runtime에 있는 원본 DB를 확보한 후 위 절차로 이전해야 한다.
- 루트 test_analyze.py는 제외된 실거래 CSV가 없어 실행 불가하다. test_normalize.py의 38개 원본 회귀 사례는 backend 테스트의 임시 복사 실행으로 통과했다. 실제 실거래 정확도/커버리지 검증과 구분한다.
- 원본 분석 코드·프론트는 변경하지 않았다. 기존 백엔드 테스트가 API·분석 계약·소유자 격리·cascade·보류 기능을 검사한다. MySQL의 같은 동작은 통합 테스트 환경에서 추가 확인해야 한다.

## MySQL 자동 검증 및 준비 상태 점검 — 2026-10-19

개인 origin의 `.github/workflows/backend-mysql.yml`은 main push/관련 PR/수동 실행에서 격리된 MySQL 8.0과 8.4 서비스 컨테이너를 각각 생성한다. 운영 비밀정보나 운영 DB를 사용하지 않는다. Python 3.12에서 기존 회귀 검사와 MySQL 재시작·이전·롤백 검사를 모두 실행하며, `--require-mysql`은 URL 미설정을 즉시 오류로 처리하고 JUnit skip 건수도 0인지 검사한다. 서비스 컨테이너는 [GitHub Actions 공식 지침](https://docs.github.com/en/actions/tutorials/use-containerized-services)에 따라 Linux runner를 사용한다.

`/health`는 기존 프로세스 상태 응답을 유지한다. `/ready`는 매번 새로운 연결로 sessions/objects/object_links 테이블을 읽고, DB 연결/스키마 접근 실패 시 내부 호스트·경로·자격증명 없이 503을 반환한다. MySQL 준비 상태 연결/읽기/쓰기 timeout은 각각 2초다. 저장소가 복구되면 다음 요청에서 다시 검사하므로 프로세스 재시작 없이 정상으로 돌아올 수 있다. 데이터 미연결 503과 정상 `{"status":"ready"}` 계약을 유지한다. 이 읽기 검사는 INSERT 권한이나 디스크 쓰기 여유까지 검증하는 쓰기 시험이 아니다.

로컬 검증: 137 passed, 3 skipped, 기존 경고 1건(9.71초). 스키마 장애 후 복구, 연결 오류 비밀정보 미노출, MySQL probe timeout을 추가 검사했다. URL 없이 `--require-mysql` 실행 시 의도대로 exit 4로 차단했다. 로컬 실제 MySQL은 여전히 미연결이며 원격 CI 실행 결과는 별도로 기록한다.


## 실제 MySQL 통합 검증 완료 — 2026-10-19

검증 코드 commit: `371ed2adbf1ef12bc5f084da540a468f6e3a6ddf`. [GitHub Actions 실행 39270463052](https://github.com/jhj120219-art/yeardream_rent_trap_detector/actions/runs/39270463052)의 두 job 모두 최종 success를 확인했다.

| CI 서비스 | 전체 백엔드 테스트 | skip | 실행 시간 |
|---|---:|---:|---:|
| MySQL 8.0 | 140 passed | 0 | 15.59초 |
| MySQL 8.4 | 140 passed | 0 | 14.84초 |

Ubuntu runner, Python 3.12.15, 격리된 일회성 rent_test DB와 합성 표본을 사용했다. 각 환경의 전체 백엔드 140개 중 MySQL 대상 테스트 3개가 실제 접속으로 실행됐으며 나머지는 기존 SQLite 회귀 및 어댑터/준비 상태 검사다. 기존 도구 deprecation 경고 각 1건.

실제 MySQL에서 확인한 범위: DDL·인증·utf8mb4 입력, HTTP 매물 등록/조회, 분석 결과 별도 저장, 백엔드 프로세스 종료 후 새 프로세스에서 동일 세션으로 매물/분석 재조회, 타 세션 격리, 매물 삭제 시 분석 cascade, SQLite→MySQL 전체 값·세션 해시·링크 보존, 비어 있지 않은 대상 거부, 잘못된 링크에서 전체 INSERT 롤백. 정상 /ready도 두 서버 프로세스에서 확인했다. MySQL 서버 자체 재시작/장애복구·운영 DB 백업 복구·실제 고객 데이터 이전·실제 가격 정확도 검증은 별도다.

따라서 이전 commit의 “MySQL 서버/자격증명 부재로 통합 검증 미완료”는 **테스트용 CI 환경에서 해소**됐다. 이 PC에 MySQL을 설치하거나 운영 설정·데이터를 바꾸지는 않았다. 프론트와 원본 분석 코드 변경 없이 수행했다.
