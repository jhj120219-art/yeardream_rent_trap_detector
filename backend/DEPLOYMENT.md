# 배포 준비 및 운영 연결 절차

현재 배포 대상·운영 MySQL·프론트 도메인은 미정이다(사용자 확인). 이 문서는 기존 외부 MySQL을 사용하는 보호된 팀 서비스의 배포 준비본이다. 실제 운영 자원 생성·고객 서비스 공개·운영 데이터 이전은 수행하지 않았다. 계정 기반 고객 인증, 운영 도메인/HTTPS, 백업 복구 및 모니터링 담당 결정은 실제 공개 전에 별도로 준비한다.

## 준비된 산출물

- `backend/scripts/deploy_preflight.py`: 구성·데이터 및 읽기 전용 MySQL 연결 검사. 기존 `Store()` 초기화를 호출하지 않으며 INSERT/DELETE/DDL을 실행하지 않는다. 출력에 URL·비밀번호·키·주소·입력 행·내부 예외를 포함하지 않는다.
- `DB_AUTO_INIT=false`: 서버 시작 시 테이블 생성 금지. 기본값 true는 기존 개발/테스트 호환용이며 배포 Compose는 false로 고정한다. 기존 스키마가 없거나 DB 접근에 실패하면 `/ready`는 503이다.
- `backend/scripts/init_mysql.py`: 관리자/마이그레이션 계정으로 명시적으로 실행하는 별도 테이블 초기화. CREATE IF NOT EXISTS만 수행한다. 운영 애플리케이션 계정에는 SELECT/INSERT/DELETE만 부여할 수 있다. 기존 테이블의 구조를 자동 업그레이드하지 않는다.
- `backend/compose.deploy.yml`: 앱만 실행, 외부 MySQL 사용, UID 10001, 읽기 전용 루트·CSV·키 파일, tmpfs, 권한 제거, 로그 회전, 로컬 8000 바인딩, 키를 읽는 /ready healthcheck. 자동 스키마 초기화·관리비 기능은 비활성화한다.
- `.dockerignore`: 실행에 필요한 소스·프롬프트만 builder에 전달한다. `.env`, 키, 인증서, 개인 DB, 원본 CSV, Git 이력, 테스트/가상환경을 이미지 컨텍스트에서 제외한다.

## 서버에서 준비할 private 파일

저장소 밖 예: `/srv/rent-private/`.

| 파일/설정 | 용도 |
|---|---|
| backend.env | backend/deploy.env.example을 참고한 앱용 DATABASE_URL 및 실제 HTTPS CORS_ORIGINS |
| clean_rent_data.csv | 분석 담당이 전달한 검증된 정제 데이터. 합성 표본을 운영 자료로 사용하지 않는다 |
| secrets/team-access.key | ASCII 40자 이상 무작위 키. 브라우저 번들에 넣지 않는다 |
| secrets/mysql-ca.pem | DB TLS 인증서 검증용 CA. DATABASE_URL의 ssl_ca 경로는 컨테이너 안 경로 |

호스트 env 파일은 소유자 전용(예: 600), 디렉터리는 접근을 제한한다. 컨테이너 UID 10001이 CSV와 키/CA를 읽을 수 있도록 서버 파일 소유자/그룹을 맞춘다. 로컬 Compose의 bind mount는 파일 소유권을 자동 변경하지 않는다. 운영 키를 무조건 644로 공개하지 않는다. CI에서는 폐기되는 무작위 검사 키에만 runner 내 읽기 권한을 적용한다.

MySQL 8.x DB는 직접 공개하지 않고 서비스에서 접근 가능한 네트워크에 둔다. 계정 비밀번호는 URL 인코딩한다. 원격 연결은 `?ssl_ca=%2Frun%2Fsecrets%2Fmysql-ca.pem`으로 서버 인증서·호스트를 검증한다. preflight는 실제 TLS cipher를 확인한다. 관리되는 신뢰 사설망에서만 명시적으로 `--allow-private-network`를 선택할 수 있으며, 이 옵션은 TLS가 검증됐음을 뜻하지 않는다.

## 배포 순서 (Linux Docker 서버 기준)

저장소 루트에서 일반 환경변수에는 파일 경로만 설정한다. 아래 예의 private 경로를 실제 서버 경로로 바꾼다.

```sh
export BACKEND_ENV_FILE=/srv/rent-private/backend.env
export RENT_DATA_FILE=/srv/rent-private/clean_rent_data.csv
export RUNTIME_SECRETS_DIR=/srv/rent-private/secrets
export BACKEND_IMAGE=rent-backend:COMMIT_SHA

docker compose -f backend/compose.deploy.yml config --quiet
docker compose -f backend/compose.deploy.yml build
```

`config` 전체 출력이나 `docker inspect`는 비밀 환경변수를 노출할 수 있으므로 공유용 로그에는 사용하지 않는다. `config --quiet`는 구조만 확인한다. 비밀정보를 Docker build arg에 넣지 않는다.

1. 기존 DB가 있으면 우선 백업과 복구 가능성을 확인한다. 실제 SQLite 자료 이전은 [MYSQL.md](MYSQL.md)의 앱 중지·백업·빈 대상 이전 절차를 따른다. 새 스키마를 준비할 때만 별도의 CREATE 권한 계정으로 초기화한다. 예를 들어 관리자 전용 `/srv/rent-private/init.env`에 DATABASE_URL을 설정하고 다음 one-off 명령을 실행한다. 런타임 backend.env에는 권한을 줄인 앱 계정을 설정한다.

```sh
docker run --rm --env-file /srv/rent-private/init.env \
  --mount type=bind,src="$RUNTIME_SECRETS_DIR",dst=/run/secrets,readonly \
  "$BACKEND_IMAGE" python -m backend.scripts.init_mysql
```

2. 앱을 켜기 전 앱 계정으로 읽기 전용 사전 검사를 실행한다.

```sh
docker compose -f backend/compose.deploy.yml run --rm --no-deps backend \
  python -m backend.scripts.deploy_preflight
```

exit 0과 `ready_for_start`가 필요하다. exit 1/blocked는 구성·연결·데이터 문제다. `--no-connect`는 로컬 파일/설정만 검사하며 성공이어도 exit 2/incomplete라서 연결 검증 완료로 오해하지 않는다. CLI에서 `--env-file`을 사용하면 기존 프로세스 환경변수가 파일 값보다 우선한다. 사전 검사는 MySQL 8.x·TLS·InnoDB 테이블·필수 컬럼 접근을 확인하지만 INSERT 권한·백업 복구·데이터 정확도·외부 도메인 DNS를 보증하지 않는다.

3. 기동 및 readiness 확인:

```sh
docker compose -f backend/compose.deploy.yml up -d --no-build --wait --wait-timeout 120
docker compose -f backend/compose.deploy.yml exec -T backend python -m backend.scripts.healthcheck
```

4. 아직 앱은 127.0.0.1:8000에만 열려 있다. 대상 서버가 정해지면 같은 호스트의 HTTPS reverse proxy 또는 호스팅 서비스 ingress를 연결한다. 다른 컨테이너의 `127.0.0.1`은 이 앱 컨테이너가 아니므로 네트워크 구성을 먼저 맞춘다. DB 포트를 공개하지 않는다. 사용자 토큰/접속키는 HTTPS 요청에서만 전달한다.
5. 관리되는 검사용 세션으로 입력→저장→분석→조회→앱 컨테이너 재시작→동일 토큰으로 재조회를 확인하고 검사 세션을 삭제한다. 운영 DB에 CI 합성 표본을 자동 주입하는 도구는 실행하지 않는다.
6. 문제 발생 시 앱을 멈추고 이전 코드 이미지로 되돌린다. DB를 삭제하거나 volume을 초기화하지 않는다. 이전 이후에 새 데이터가 생겼다면 DB를 과거 백업으로 무조건 덮어쓰지 않고 별도로 대조한다. 스키마 변경이 없는 이번 이미지는 기존 저장 구조를 그대로 사용한다.

## CI에서 확인하는 범위

기존 MySQL 8.0/8.4 전체 회귀에 실제 DB 읽기 전용 preflight를 추가한다. 8.4 job에서는 Docker 이미지를 빌드한 뒤 배포 Compose를 직접 실행한다. CI 전용 localhost DB·임시 CSV·무작위 접속키를 사용하며, 예외 옵션으로 CI의 사설 Docker 네트워크를 허용한다. 컨텍스트에 심은 가짜 비밀파일이 이미지에 없는지, 비루트/read-only 실행, 접속 보호, 관리비 보류, 컨테이너 restart 후 입력/분석 보존과 세션 삭제를 검사한다. 운영 주소나 자격증명은 사용하지 않는다. 실제 운영 TLS·운영 환경 연결·고객 배포와 구분한다.

구현 참고: [Docker build context](https://docs.docker.com/build/concepts/context/), [Compose 서비스](https://docs.docker.com/reference/compose-file/services/).

## 이번 실행 결과 — 2026-10-19

운영 배포 대상·MySQL 서버·프론트 도메인은 아직 없다는 사용자 답변에 따라 실제 자원을 생성하거나 공개 배포하지 않았다. 이 PC에도 운영 DATABASE_URL/환경 파일/Docker가 없었다. 실제 운영 연결은 미검증이며 준비 검사에서 blocked로 표시했다.

검증 코드 `38647e9`, [CI 실행 39272224153](https://github.com/jhj120219-art/yeardream_rent_trap_detector/actions/runs/39272224153): MySQL 8.0 **152 passed, 0 skipped, 13.62초**, MySQL 8.4 **152 passed, 0 skipped, 16.68초**. 기존 Starlette/httpx 경고 각 1건. 8.4 job에서 Docker image build 및 실제 배포 Compose 검사가 성공했다.

- [x] Compose 구조 검증, 별도 명시적 스키마 초기화, 읽기 전용 preflight 성공.
- [x] 소스 경로에 심은 가짜 `.env`와 private CSV가 이미지에 없는 것을 확인.
- [x] 비루트 UID·read-only 컨테이너·접속키 healthcheck로 healthy 기동.
- [x] 키 없는 요청401, 관리비 비활성화, 매물/분석 저장 확인.
- [x] 앱 컨테이너 restart 후 같은 세션으로 매물·분석 원문 일치.
- [x] 검사 세션 삭제 및 임시 앱 컨테이너 정리.
- [ ] 실제 운영 서버·프론트 도메인·운영 MySQL·CA·정제 CSV·최소 권한 계정 연결.
- [ ] 운영 MySQL 서버 자체 재시작, 백업 복원, 운영 HTTPS/모니터링·장애 대응 확인.

첫 CI에서는 최신 PyMySQL의 자동 TLS 암호화 때문에 “CA 미설정이면 반드시 평문”이라는 테스트 가정이 틀려 실패했다. 단순 cipher 존재만으로 통과하지 않고, 실제 암호화와 명시적 인증서/호스트 검증 옵션을 모두 요구하도록 수정한 뒤 전체 CI를 통과했다. 사설망 허용 옵션은 CI 네트워크에서만 명시적으로 사용했으며 운영 CA/TLS 검증 완료로 계산하지 않는다.
