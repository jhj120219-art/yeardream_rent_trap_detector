# 광고 관리비 입력·표시 — 후속 연결 안내

관리비를 받아 적는 것과 적정한지 계산하는 것은 다릅니다. **광고에 적힌 내용은 입력·저장·표시합니다. 관리비 비교와 예상 비용 계산은 보류합니다.**

## 프론트에 추가해주세요

| 입력칸 | 입력 방법 |
| --- | --- |
| 월 관리비 | 만원 단위. 미기재·모름이면 null, 실제 무료라고 적혔을 때만 0 |
| 전기·수도·가스·인터넷·청소·공용관리·기타 | 각각 포함 / 별도 납부 / 모름 선택 |
| 항목별 월 금액 | 광고에 따로 명시된 경우만 입력. 포함이라고 해서 금액을 0으로 채우지 않음 |
| 기타 항목명 | 예: 주차. 광고에 적힌 이름을 입력 |
| 관리비 설명 | 광고 문구를 입력. 예상 금액이나 추정 설명을 붙이지 않음 |

기본 선택은 모름입니다. 인터넷 사용 가능은 관리비 포함이라는 뜻이 아닙니다. 광고에 부과 주기가 없거나 월 금액인지 확실하지 않으면 금액을 비워두고 설명에 적습니다. 개인 이름·전화번호 등 불필요한 정보는 입력하지 않습니다.

## 기존 저장 요청의 options에 추가합니다

기존 POST /listings와 GET /listings/{id}/report를 그대로 사용합니다. 2026-10-20 후속 변경으로 원본 JSON과 함께 관리비 총액·항목을 별도 관계형 테이블에도 저장합니다. [항목별 DB 저장](MAINTENANCE_DB.md)을 참고하세요. 사용자 확인 전 입력은 미확인으로 표시하며 월세 분석은 기존처럼 차단합니다. 저장된 내용을 수정할 때는 새 매물에 previous_listing_id를 연결하는 기존 규격을 사용합니다.

```json
{
  "maintenance_10k_krw": 7,
  "electricity_in_maintenance": "SEPARATE_CHARGE",
  "electricity_10k_krw": null,
  "water_in_maintenance": "INCLUDED",
  "water_10k_krw": 1,
  "gas_in_maintenance": "UNKNOWN",
  "gas_10k_krw": null,
  "internet_status": "INCLUDED",
  "internet_10k_krw": null,
  "cleaning_in_maintenance": "INCLUDED",
  "cleaning_10k_krw": null,
  "common_in_maintenance": "UNKNOWN",
  "common_10k_krw": null,
  "other_in_maintenance": "SEPARATE_CHARGE",
  "other_cost_label": "주차",
  "other_10k_krw": 3,
  "maintenance_note": "광고에 수도 1만원 포함, 주차 3만원 별도라고 표시됨"
}
```

위 내용은 options 부분만 보여주는 가상 예시입니다. 금액은 만원, 선택값은 INCLUDED / SEPARATE_CHARGE / UNKNOWN입니다. 기존 internet_status의 AVAILABLE / NOT_AVAILABLE도 저장할 수 있지만 관리비 포함 여부는 UNKNOWN으로 표시합니다. 음수·불리언·무한대·잘못된 선택값은 422입니다. 모르는 값에 문자열 '미기재' 대신 null을 보냅니다.

## 결과 화면에 표시할 위치

`report.advertised_costs`에서 관리비 총액, items, note, 사용자 확인 상태를 읽습니다. 원본 입력은 GET /listings/{id}의 input.options에 그대로 남습니다.

- maintenance_10k_krw: 광고 월 관리비
- items[].item: ELECTRICITY / WATER / GAS / INTERNET / CLEANING / COMMON / OTHER
- items[].status: 포함 / 별도 / 모름
- items[].quoted_monthly_10k_krw: 광고에 명시한 월 금액, 없으면 null
- state: USER_CONFIRMED 또는 NEEDS_USER_CONFIRMATION
- comparison_state: ON_HOLD

공유 모드에서 기존 maintenance / utility_costs / monthly_cost / utility_estimate는 계속 ON_HOLD입니다. 이 항목들을 다시 켜지 않고, 별도 advertised_costs만 광고 정보로 보여주세요. 총액에 항목별 금액을 다시 더하지 않고, 월세 적정성 분석에도 섞지 않습니다. 서버가 null로 보낸 가격은 '미기재'로 표시해주세요. 사용자 확인은 사실 검증·공식 자료 확인을 뜻하지 않습니다.

## 사용자님이 꼭 해주실 일

1. 프론트 담당자에게 이 안내와 최신 팀 저장소를 전달해주세요. 입력칸을 추가하고 결과에 advertised_costs를 표시해달라고 부탁하시면 됩니다.
2. 프론트 실행 주소가 바뀌면 정확한 주소를 알려주세요. 서버 접속 허용 설정에 필요합니다. 팀 접속키는 기존 방식대로 1:1 전달합니다.

이 관리비 입력 기능에는 새 외부 API 키나 추가 자료가 필요하지 않습니다. 분석 담당자에게 관리비 평균을 지금 요청할 필요도 없습니다. 주소·캡처의 실제 API 검증과 상시 서버 배포는 별도 남은 작업입니다. 팀 메시지는 직접 전송하지 않았습니다.
