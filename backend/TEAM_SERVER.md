# 다른 장소에서 함께 쓰는 팀 테스트 서버

2026-10-19. 관리비·공과금 비교는 분석 담당 자료 검증까지 보류한다.

## 누구나 이해하는 연결 구조

프론트 화면 → HTTPS 접속 주소 → 이 PC의 백엔드 → 팀 테스트용 DB.

프론트는 DB 파일을 직접 열지 않는다. 백엔드 API에 저장·조회 요청을 보낸다. 각 사용자는 자기 세션으로 등록한 자료만 조회·삭제할 수 있다. 기존 개인 DB는 복사하거나 외부에 연결하지 않는다.

현재는 계정 없이 가능한 Cloudflare Quick Tunnel을 통한 **팀 개발 테스트**다. 이 PC와 서버 프로그램이 켜져 있어야 한다. 다시 시작하면 접속 주소가 바뀐다. 상시 운영 서버·고정 주소·실제 고객용 로그인은 아직 준비되지 않았다. 공식 조건: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/

## 프론트 담당자가 할 일

1. PM에게 현재 접속 주소와 `team-access.key` 파일을 개인 전달로 받는다. 키를 단체 채팅·저장소·스크린샷에 올리지 않는다.
2. 개발 화면은 `http://localhost:5173` 또는 `http://localhost:3000`에서 실행한다. 다른 화면 주소를 사용하면 그 주소를 PM에게 알려 CORS 허용 목록에 추가한다.
3. 모든 실제 API 요청에 `X-Team-Key` 헤더로 접속키를 전달한다. 최초 `POST /sessions` 응답의 `token`은 이후 요청의 `Authorization: Bearer <token>`에 넣는다.
4. 기존 v1.1 매물 입력 계약으로 `POST /listings` → `POST /listings/{id}/analyses` → `GET /listings/{id}/report`를 연결한다. 사용자 확인 전에는 분석하지 않는다.
5. 결과 화면은 `property`, `rent`를 사용한다. `maintenance`, `utility_costs`, `monthly_cost`, `utility_estimate`는 `{ "state": "ON_HOLD" }`이며 화면에 비용 판단을 표시하지 않는다.
6. 화면에서 사용자별 자료 삭제와 세션 종료(`DELETE /sessions/current`)를 연결한다. 세션 토큰을 잃으면 기존 자료에 다시 접근할 수 없다. 아직 계정 로그인 서비스가 아니다.

접속키는 사용자가 테스트 시작 시 직접 입력하도록 한다. 프론트 소스, 공개 환경 변수(`VITE_*` 등), 배포 번들에 고정해서 넣지 않는다. 키는 팀 테스트용 공통 출입키이며 사용자 로그인 토큰과 다르다. 브라우저가 보내는 키는 사용자가 개발자 도구에서 볼 수 있으므로 실제 고객용 인증으로 사용하지 않는다.

최소 연결 예시(개발 코드):

```javascript
const base = /* PM에게 받은 HTTPS 주소 */;
const teamKey = /* 사용자가 테스트 시작 시 입력한 키, 메모리에서만 보관 */;
const first = await fetch(`${base}/sessions`, {
  method: 'POST', headers: {'X-Team-Key': teamKey}
});
if (!first.ok) throw new Error('접속 주소와 팀 접속키를 확인해 주세요.');
const {token} = await first.json();
const headers = {'X-Team-Key': teamKey, Authorization: `Bearer ${token}`,
  'Content-Type': 'application/json'};
// fetch(`${base}/listings`, {method:'POST', headers, body:JSON.stringify(v11Input)})
```

오류: 401은 팀 키 또는 세션 토큰 확인, 404는 해당 세션 자료 없음, 422는 입력값 확인, 503은 데이터/API 키 미연결 또는 보류 기능이다. `/health`, `/capabilities`, `/openapi.json`, `/docs`도 팀 접속키가 필요하다. 기본 Swagger 페이지는 헤더 입력 없이 열 수 없으므로 프론트는 헤더를 지원하는 API 도구로 OpenAPI를 받는다.

## 서버와 DB 설정

- 실행 코드: `backend/scripts/team_server.py`. 기존 가상환경에서 모듈로 실행한다.
- 서버는 `127.0.0.1:8012`만 사용한다. DB 포트, 공유기 포트, 외부 방화벽 인바운드는 열지 않는다.
- `TEAM_SHARED_MODE=true`, `TEAM_ACCESS_KEY_FILE=<보호된 파일>`, `MAINTENANCE_ENABLED=false`.
- `BACKEND_DB_PATH=<runtime>/team.sqlite3`, `RENT_CLEAN_CSV=<기존 정제 CSV 경로>`.
- `CORS_ORIGINS`는 `<runtime>/frontend-origins.txt`의 명시적 주소 목록으로 설정한다. `*`는 공유 모드에서 시작 실패한다. 변경 후 재시작해야 한다.
- runtime은 저장소·OneDrive 밖의 로컬 폴더다. 현재 PC의 실제 위치는 시작 버튼 옆 `서버폴더열기.cmd`로 확인한다. 접속키·DB·백업·실행 로그는 Git에 넣지 않는다.
- SQLite WAL·외래키 사용. 사용자 세션, 입력 매물, 추출 결과, 분석 결과를 저장한다. 원본 이미지 저장은 하지 않는다. 분석용 CSV는 읽기 전용으로 기존 파일을 사용한다.
- 시작 전 기존 DB, 시작 직후, 실행 중 24시간마다, 정상 종료 시 SQLite 온라인 백업을 만든다. 각 백업에 `integrity_check`를 수행한다. 갑작스러운 전원 종료 시 마지막 종료 백업은 수행되지 않는다. 같은 디스크의 백업이므로 디스크 고장 복구 대책은 별도로 필요하다.
- 복구는 서버 종료 후 검증한 백업을 별도 DB 경로로 복사하여 `BACKEND_DB_PATH`를 지정하고 확인한다. 실행 중인 DB를 덮어쓰지 않는다. 이번 검증은 백업 파일 무결성과 저장 데이터 읽기를 확인했으며 장애 상황 전체 복구 훈련은 아니다.
- 공식 cloudflared 2026.10.1 Windows amd64, 배포 SHA-256을 코드에 고정하고 실행 전 검증한다. 관리자 설치·시스템 PATH 변경은 하지 않는다.

## 확인한 것과 남은 것

공개 HTTPS 경로로 팀 키 없는 요청 차단, CORS, 세션 발급, 가상 입력 저장 → 실제 정제 실거래 비교 → 저장 결과 조회, 다른 세션 조회·삭제 차단, 연쇄 삭제, 세션 삭제, 관리비 보류, 온라인 백업 무결성을 검사했다. 검사용 가상 매물·세션은 삭제했다. 실제 고객 매물을 등록하거나 정확도를 측정한 검증이 아니다.

남은 것: 프론트 담당 PC에서 화면 연결 확인, 주소·이미지 외부 API의 실제 키 검증, 상시 서버 계정과 배포 위치 결정. 현 분석 계약은 동 → 조건 완화 → 구 비교이며 같은 건물 우선 비교와 비교 거래 개별 목록은 연결되지 않았다. 분석 담당 최신 시연 결과와 실제 전달 코드의 차이는 담당자 협의가 필요하다.

PM 요청 초안: “테스트 서버 주소와 접속키 파일을 따로 전달하겠습니다. 프론트는 직접 입력·사용자 확인·월세 결과·삭제를 먼저 연결하고 화면 실행 주소를 알려주세요. 관리비는 계속 보류합니다. 분석 담당자는 같은 건물 우선 비교와 거래 목록이 포함된 최신 실행 코드·입출력 계약을 전달해 주세요.”
