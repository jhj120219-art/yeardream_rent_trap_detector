# MySQL 8.x 전환 및 영속성 검증

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
