> **2026-10-20 wlsdu PC 복구:** 이전 jhj12 PC의 임시 주소는 DNS NXDOMAIN으로 확인됐다. 현재 실행 환경은 `C:/Users/wlsdu/AppData/Local/YeardreamRentBackend`이며 최신 주소는 이 폴더의 `접속주소.txt`, 접속키는 `team-access.key`다. 문서 아래 jhj12 경로는 과거 환경이다. 새 키는 별도 1:1로 전달하며 채팅에 붙인 이전 값을 재사용하지 않는다. 시작 도구는 같은 폴더의 `server-start.cmd`, API 종료 도구는 `server-stop.cmd`다. 이 PC가 켜져 있고 절전 상태가 아니어야 접속된다. 원본 입력·DB·계정·실행 파일은 Git pull로 이전되지 않는다.

# 팀 연결 안내 — 2026-10-20

**관리비 입력 후속 반영:** [광고 관리비 입력·표시 안내](ADVERTISED_COSTS.md). 관리비 비교는 보류하지만 광고에 적힌 총액·포함 항목·명시 금액·설명은 입력·저장·표시합니다. report의 `advertised_costs`를 사용해주세요. 기존 보고서에서 관리비 전체를 제외하라는 안내보다 이 후속 안내가 우선합니다.

쉽게 읽는 공유 보고서: [화면용 HTML](reports/team_connection_20261020/team_connection_report.html) · [공유용 PDF](reports/team_connection_20261020/team_connection_report.pdf). 담당별 현재 현황과 다음 해야 할 일을 정리했습니다.

## 지금 어디까지 이어졌나요?

| 담당 | 확인한 상태 | 다음 할 일 |
| --- | --- | --- |
| 분석 | ZIP의 분석 프로그램을 백엔드가 실제 호출함 | 개별 비교 거래 목록을 반환하는 규격, 면적·판정 보호 규칙 확인 |
| 백엔드 | 입력 → MySQL 저장 → 동네 분석 → 결과 저장·조회 검증 완료 | 프론트 실행 주소가 달라지면 허용 주소 등록 |
| 프론트 | ZIP 원본은 오프라인 시안. 이후 실제 화면의 연결 완료 여부는 별도 검증 필요 | 아래 연결 파일을 화면 버튼에 연결하고 실제 화면에서 확인 |
| 사용자님 | 서버 주소와 접속키를 프론트 담당자에게 따로 전달 | 키 발급·코딩은 필요 없음 |

최근 반영 ZIP: `ai-wolse-trap-detector-main (1).zip`, 팀 커밋 `7c90b59`, SHA256 `6c2cb31ba1eb7445c1e6865c8f7fa5e418f9479c95865b50ae4a86efa06e3fb1`. 분석·프론트 원본을 보존하고 백엔드 변경은 검토 후 통합했다.

현재 비교는 같은 법정동 → 조건 완화 → 같은 구다. 같은 건물 우선 비교와 관리비 비교·예상 계산은 보류한다. 광고 관리비 입력·저장·표시는 지원한다. 개별 비교 거래 목록은 분석에서 반환되지 않아 제공하지 않는다. 과거 분석 평가 수치를 새 백엔드의 정확도로 표시하면 안 된다.

## 프론트 담당자에게 전달할 것

1. 최신 서버 주소: 현재 PC runtime의 `접속주소.txt`에서 확인한다. 재시작하면 바뀔 수 있다.
2. 접속키 파일: `C:/Users/wlsdu/AppData/Local/YeardreamRentBackend/team-access.key`를 신뢰할 수 있는 1:1 수단으로 따로 전달한다. GitHub·공유 문서에 넣지 않는다.
3. 연결 파일: 이 폴더의 `frontend_api_example.mjs`. 기존 프론트 문서가 가리킨 `.js` 예제는 이 작업 저장소에 없었으므로 실제 검증한 이 파일을 사용한다.

키는 팀 개발용 서버 비밀번호다. OpenAI·카카오·DB 비밀번호를 프론트 담당자에게 전달하는 것이 아니다. 개발 중 키를 입력받아 메모리에서만 사용한다. 일반 사용자에게 공개하는 운영 인증 방식은 별도 설계가 필요하다.

## 버튼에 연결하는 방법

```javascript
import { createRentClient } from './frontend_api_example.mjs';

// 두 값은 개발용 접속 화면에서 입력받는다. 소스에 실제 키를 적지 않는다.
const api = createRentClient({ baseUrl: serverAddress, teamKey: enteredTeamKey });
const { capabilities, locations } = await api.start();
// locations의 구·법정동 목록으로 선택칸을 구성한다.
// 폼 값을 기존 schema_version/listing/options/confirmation 형식으로 만든다.
const task = api.createComparison(confirmedInput);
const report = await task.run(step => showProgress(step));
showReport(report); // property.input, rent.result를 사용한다.
// 실패했을 때는 같은 task.run()을 다시 호출한다.
// 입력을 수정했다면 새 task를 만든다. 전송 중 버튼을 비활성화한다.
```

한 번 만든 api와 task를 화면 상태에 보관한다. 버튼을 누를 때마다 새 클라이언트·새 작업을 만들면 재시도 보호를 활용할 수 없다. 네트워크 실패 때 키·토큰을 로그에 출력하지 않는다. 이용표를 잃으면 기존 자료를 계정으로 복구하는 기능은 없다. 창을 닫을 때 삭제를 자동 호출하지 않는다.

HTTP 오류는 `error.status`, 입력 오류 내용은 `error.details`로 확인한다. HTTP 성공이어도 `report.rent.result.status`가 자료 부족·확인 필요일 수 있다. 가격이 null이면 0원으로 표시하지 않는다. 차이율은 비율이므로 화면에서 100을 곱해 %로 표시한다. 신뢰도 등급을 사기 확률로 표시하지 않는다.

`http://localhost:5173`, `http://localhost:3000`, 현재 팀 미리보기 주소가 허용돼 있다. 파일을 더블클릭한 `file://` 화면은 실제 연결 검증용이 아니다. 프론트 실행 주소가 달라지면 백엔드에 정확한 주소를 알려준다.

## 입력 예시와 선택 기능

```json
{
  "schema_version": "1.1",
  "listing": {
    "district_code": "11620", "legal_dong_code": "1162010100",
    "building_type": "APARTMENT", "area_m2": 59.9, "area_basis": "EXCLUSIVE",
    "deposit_10k_krw": 5000, "rent_10k_krw": 80,
    "built_year": 2005, "floor": 5, "floor_type": "GROUND", "floor_source": "USER_CONFIRMED"
  },
  "options": {},
  "confirmation": {"user_confirmed": true, "input_source": "ADDRESS_MANUAL", "confirmed_fields": ["floor"]}
}
```

예시는 형식 확인용이며 실제 매물이 아니다. 금액은 만원, 면적은 ㎡다. 모르는 값은 null/UNKNOWN 계약을 사용하며 임의로 채우지 않는다. 관리비·옵션으로 월세 비교 가격을 보정하지 않는다.

주소·이미지 입력 API는 기존 서버에 있으나 실제 외부 API 검증과 프론트 연결은 별개다. `/capabilities`의 address_configured/vision_configured가 false면 사용할 수 있다고 안내하지 않는다. 이미지 추출은 `/extractions` → `/extractions/{id}/listing-draft` → 사용자 수정·확인 → `/listings` 순서다. 추출 초안을 그대로 분석하지 않는다. 이미지 초안에서 저장할 때 source_extraction_id와 IMAGE_REVIEWED를 함께 전달한다.

## 검증 결과와 남은 확인

백엔드 검사 169개 통과, 연결 파일의 재시도·입력 확인 검사 2개 통과. 실제 인터넷 서버에서 이 JavaScript 파일로 저장·분석·조회·세션 삭제까지 확인했다. 실제 데이터 결과는 같은 동 비교, 표본 42건이었다. 이 표본은 정확도 평가가 아니다. 프론트 허용 주소·접속키 누락 차단·중복 저장 방지도 인터넷 요청으로 확인했다.

**프론트 실제 화면에 버튼을 연결한 상태는 아직 검증하지 않았다.** 프론트 담당자는 정상 결과·입력 확인·자료 부족·연결 실패 후 재시도를 화면에서 확인해야 한다. 분석 담당자에게는 개별 거래 행 반환과 기존 판정 보호 규칙 확인을 요청한다. 건물 동수 CSV와 관리비는 지금 요청할 작업에서 제외한다. 팀 메시지는 직접 전송하지 않았다. 이 PC를 끄면 접속이 중단되는 임시 서버이며 상시 서버 배포는 완료하지 않았다.


## 연결 오류 추적 — 요청 ID

백엔드 응답의 `X-Request-ID`를 읽어 HTTP 상태·실패한 동작과 함께 공유합니다. 허용된 프론트 origin에서 읽도록 CORS expose 헤더를 지원합니다. ID는 서버가 매 요청 새로 발급하며 클라이언트가 임의로 지정한 값은 사용하지 않습니다. 서버 로그는 경로 템플릿·상태·처리 시간만 남기고 키·토큰·입력·쿼리는 기록하지 않습니다. 적용 전 실행 중인 서버는 재시작이 필요합니다. 기존 응답 JSON 계약은 변경하지 않습니다.


## 연결 클라이언트 오류·시간 제한 — 2026-10-21

`createRentClient`는 기본 30초 안에 응답 본문까지 받지 못하면 요청을 중단합니다. `timeoutMs`로 최대 300000ms까지 조절할 수 있습니다. 시간 초과는 서버 작업 취소·저장 실패를 뜻하지 않습니다. 기존 `createComparison` 작업 객체의 `run()`을 다시 호출하면 같은 재시도 키로 저장·분석을 이어갑니다. 입력을 바꿨다면 새 작업 객체를 만듭니다.

- HTTP 오류: `error.status`, `error.details`, `error.requestId`를 제공합니다. 요청 ID는 서버 형식이 맞는 경우에만 사용합니다.
- 시간 초과: `error.code === 'TIMEOUT'`.
- 네트워크·CORS·응답 파싱 실패: `error.code === 'NETWORK_OR_RESPONSE_ERROR'`. 브라우저가 구분 정보를 주지 않는 경우 DNS·CORS 중 하나로 단정하지 않습니다.
- 원시 전송 오류·키·헤더·입력 본문은 오류 객체에 복사하지 않습니다. `details`도 공개 로그에 통째로 출력하지 않습니다.

성공 응답 JSON과 세션·중복 방지 계약은 유지합니다. 프론트가 최신 연결 모듈을 가져와야 적용됩니다. 서버만 Git pull해도 기존 시안에 자동 반영되지는 않습니다.
