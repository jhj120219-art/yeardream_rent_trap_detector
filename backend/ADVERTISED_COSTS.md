> **최신 입력·결과 확정(2026-10-21):** 고객은 5개 항목 체크 + 선택된 항목의 관리비 총액 한 칸만 입력합니다. 결과는 체크/미체크 항목의 분석 참고비용을 분리합니다. [새 연결 규격](CHECKBOX_MAINTENANCE.md)이 이전 상세금액 입력 안내보다 우선합니다. 실제 분석값 미연결·아파트 정책·지원 범위는 별도 미완료/논의 중입니다.

> **2026-10-21 논의 중:** 관리비 기본안은 전기·수도·가스·인터넷·기타 5항목입니다. 아파트의 청소·공용관리비를 별도 항목으로 추가할지, 모든 주택유형에서 기타로 통일할지는 미확정입니다. 결정 전 현재 FIVE_ITEMS_V1 구현을 유지하고 DB·API 항목을 임의로 늘리거나 기존 세부내역을 삭제하지 않습니다.

# 관리비 5항목 입력·저장·표시 — 2026-10-21

현재 항목은 **전기세·수도세·가스비·인터넷·기타 관리비** 5가지입니다. 청소·공용관리·주차 등은 기타 관리비의 설명으로 입력합니다. 광고 입력 저장과 실제 관리비 추정 계산은 구분하며, 비교·예상 계산은 검증 전까지 ON_HOLD입니다.

| 화면 항목 | API 항목 | 포함 여부 필드 | 광고 명시 월 금액(만원) |
|---|---|---|---|
| 전기세 | ELECTRICITY | electricity_in_maintenance | electricity_10k_krw |
| 수도세 | WATER | water_in_maintenance | water_10k_krw |
| 가스비 | GAS | gas_in_maintenance | gas_10k_krw |
| 인터넷 | INTERNET | internet_status | internet_10k_krw |
| 기타 관리비 | OTHER | other_in_maintenance | other_10k_krw |

- 총 관리비: maintenance_10k_krw. 기타 설명: other_cost_label. 전체 광고 문구: maintenance_note.
- 선택값: INCLUDED / SEPARATE_CHARGE / UNKNOWN. 모르는 금액은 null, 실제 무료로 명시된 경우만 0.
- 총액에서 알려진 항목을 빼서 기타 금액을 임의 생성하지 않습니다. 포함 금액을 총액에 다시 더하지 않습니다.
- 인터넷 AVAILABLE은 사용 가능이라는 뜻이며 포함 여부는 UNKNOWN으로 표시합니다.

## 연결과 표시

기존 POST /listings의 options에 넣고, 사용자 확인 후 분석합니다. 결과는 GET /listings/{id}/report의 advertised_costs를 사용합니다. items는 위 순서로 정확히 5개이며 category_version=FIVE_ITEMS_V1입니다. /capabilities의 advertised_cost_categories·advertised_cost_category_version으로 적용 여부를 확인할 수 있습니다.

```json
{
  "maintenance_10k_krw": 7,
  "electricity_in_maintenance": "SEPARATE_CHARGE", "electricity_10k_krw": null,
  "water_in_maintenance": "INCLUDED", "water_10k_krw": 1,
  "gas_in_maintenance": "UNKNOWN", "gas_10k_krw": null,
  "internet_status": "INCLUDED", "internet_10k_krw": null,
  "other_in_maintenance": "INCLUDED", "other_10k_krw": null,
  "other_cost_label": "청소·공용관리 포함, 상세 금액 미기재",
  "maintenance_note": "광고에 적힌 내용만 입력한 가상 예시"
}
```

위 예시는 options 부분이며 실제 광고가 아닙니다. 원본 입력은 input.options에 보존합니다. 월세 결과는 rent.result에서 가격 범위·차액·차이율·표본 수·조건·신뢰도·보류 사유를 읽습니다. 개별 비교 거래 목록은 분석 원본이 아직 반환하지 않아 NOT_PROVIDED_BY_ANALYSIS이며, 만든 목록을 실제 거래처럼 표시하지 않습니다.

## 예전 7항목 자료

기존 청소(CLEANING)·공용(COMMON) DB 행과 원본 JSON을 삭제하지 않습니다. 기존 행 7개를 읽어도 화면 주항목은 5개입니다. 옛 청소·공용 금액이 있으면 OTHER.legacy_components에 원래 값을 보존하고 needs_review=true로 표시합니다. 기존 기타와 중복될 수 있으므로 합산한 금액이나 포함 여부를 만들지 않습니다. 프론트는 기타에 “기존 세부내역 확인 필요”를 표시하고 세부내역을 펼쳐 보여줄 수 있습니다. 사용자가 확인해 수정하면 새 매물+previous_listing_id로 저장합니다.

신규 DB 저장은 총액 1행 + 항목 5행입니다. 기존 테이블 제약의 CLEANING·COMMON 허용은 과거 기록 보존용이며 새 화면의 항목이 아닙니다. 기존 7행을 강제로 지우거나 schema를 축소하지 않아 별도 파괴적 DB 변경이 필요 없습니다.

## 적용 상태

개발·검증 결과와 집 서버 적용은 별개입니다. 집 서버가 FIVE_ITEMS_V1을 반환하는지 확인해야 운영 반영 완료입니다. Git push만으로 실행 중인 집 서버가 변경되지는 않습니다. 실제 화면에서 5항목·미기재/0원·기타 확인 필요·재시도·저장 전후 일치를 확인해주세요. 키는 별도 전달합니다.
