# 팀 연결 안내 — 2026-10-20

**관리비 입력 후속 반영:** [광고 관리비 입력·표시 안내](ADVERTISED_COSTS.md). 관리비 비교는 보류하지만 광고에 적힌 총액·포함 항목·명시 금액·설명은 입력·저장·표시합니다. report의 `advertised_costs`를 사용해주세요. 기존 보고서에서 관리비 전체를 제외하라는 안내보다 이 후속 안내가 우선합니다.

쉽게 읽는 공유 보고서: [화면용 HTML](reports/team_connection_20261020/team_connection_report.html) · [공유용 PDF](reports/team_connection_20261020/team_connection_report.pdf). 담당별 현재 현황과 다음 해야 할 일을 정리했습니다.

## 지금 어디까지 이어졌나요?

| 담당 | 확인한 상태 | 다음 할 일 |
| --- | --- | --- |
| 분석 | ZIP의 분석 프로그램을 백엔드가 실제 호출함 | 개별 비교 거래 목록을 반환하는 규격, 면적·판정 보호 규칙 확인 |
| 백엔드 | 입력 → MySQL 저장 → 동네 분석 → 결과 저장·조회 검증 완료 | 프론트 실행 주소가 달라지면 허용 주소 등록 |
| 프론트 | ZIP에는 오프라인 화면 시안만 있음. 실제 서버 연결은 아직 없음 | 아래 연결 파일을 화면 버튼에 연결하고 실제 화면에서 확인 |
| 사용자님 | 서버 주소와 접속키를 프론트 담당자에게 따로 전달 | 키 발급·코딩은 필요 없음 |

확인한 ZIP: `ai-wolse-trap-detector-main (2).zip`, SHA256 `4c442a81e45bb4637e170ca2a42bfbbca21b7f4f747c7b0726952adfcf732189`. 원본 프론트·분석 파일은 수정하지 않았다.

현재 비교는 같은 법정동 → 조건 완화 → 같은 구다. 같은 건물 우선 비교와 관리비 비교·예상 계산은 보류한다. 광고 관리비 입력·저장·표시는 지원한다. 개별 비교 거래 목록은 분석에서 반환되지 않아 제공하지 않는다. 과거 분석 평가 수치를 새 백엔드의 정확도로 표시하면 안 된다.

## 프론트 담당자에게 전달할 것

1. 최신 서버 주소: 작업 폴더의 `deliverables/team_server/접속안내.txt`에서 확인한다. 재시작하면 바뀔 수 있다.
2. 접속키 파일: `C:/Users/jhj12/AppData/Local/YeardreamRentBackend/team-access.key`를 신뢰할 수 있는 1:1 수단으로 따로 전달한다. GitHub·공유 문서에 넣지 않는다.
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
