# 머신 관리비 참고 비용 미리보기 (백엔드 + 머신 연동 시연)

저장된 매물의 광고 관리비 입력(5항목 `FIVE_ITEMS_V1`)을 머신(`machine/analysis_internal/utility`)의 `run_maintenance()`에 넘겨, **전기 · 수도 · 가스 · 인터넷의 서울 비슷한 가구 기준 참고 비용**을 보여 주는 시연용 엔드포인트입니다. 기존 `utility-estimates`(고정 시나리오 견적)와 별개이며, 결과를 DB에 저장하지 않습니다. 기본으로 **꺼져 있습니다.**

> 참고 추정값입니다. 실제 청구액 · 평균 청구액 · 정상 관리비가 아니며 "부당/과다"를 판정하지 않습니다. 기타(청소 · 공용 등)는 광고에 명시된 금액만 표시하고 총액에서 역산하지 않습니다.

## 켜는 방법

| 환경변수 | 값 | 설명 |
|---|---|---|
| `MACHINE_MAINTENANCE_PREVIEW` | `true` | 미리보기 엔드포인트 켜기 (`/capabilities`의 `machine_maintenance_preview`로 확인) |
| `ENERGY_REFERENCE_CSV` | (선택) | 서울 가구에너지패널 14차 집계표는 저장소의 `machine/analysis_internal/utility/reference_data/energy_reference_2023.csv`에 들어 있어 따로 설정하지 않아도 됩니다. 다른 파일을 쓰려면 경로를 지정하세요 |

```bash
# 저장소 루트에서 한 번에 보기 (임시 DB, 가상 매물, MySQL 불필요)
ENERGY_REFERENCE_CSV=... python -m backend.scripts.demo_machine_preview      # 결과: backend/examples/machine_preview_demo.md / .json
# 서버로 쓰기
MACHINE_MAINTENANCE_PREVIEW=true ENERGY_REFERENCE_CSV=... uvicorn backend.app.main:app
```

도커 이미지에는 머신 관리비 코드, 공개 요금표 · 요약 JSON, 서울 집계표(`reference_data/energy_reference_2023.csv`)가 들어갑니다(`Dockerfile.dockerignore`에 허용 추가). 파일을 찾지 못하면 서버는 죽지 않고 응답에 `errors[0].code = MISSING_DATA_FILE`과 준비 방법을 담아 돌려줍니다.

## 요청 · 응답

`POST /listings/{listing_id}/maintenance-reference` (세션 토큰 필요)

```json
{ "target_month": 10, "household_size": 1, "area_m2": 20.0, "heating_type": "개별 도시가스", "gas_user": "예",
  "metering": "INDIVIDUAL", "acknowledge_reference_limits": true }
```

- 매물이 **확인(user_confirmed)된 유효한 매물**이고 `acknowledge_reference_limits`가 `true`여야 계산합니다. 아니면 `state: NEEDS_REVIEW`.
- `area_m2`를 비우면 매물의 전용면적(`area_basis=EXCLUSIVE`)을 씁니다. `household_size`, `heating_type`, `gas_user`를 모르면 그 관점은 건너뛰고(임의 가정 없음) 해당 항목을 보류하며 확인 질문을 돌려줍니다.
- 응답 `state`: `CALCULATED` / `NEEDS_REVIEW` / `ERROR`. `result`는 머신의 `maintenance.v1` 결과입니다.

| 필드 | 의미 |
|---|---|
| `result.status` | `REFERENCE_ONLY`(참고 표시) / `REVIEW_REQUIRED`(입력 확인 필요) / `INSUFFICIENT_DATA`(정보 부족) |
| `result.utility_estimates[]` | 항목별 `reference_low_krw` ~ `reference_high_krw`(서로 다른 집단 평균을 각각 환산한 값들의 최소~최대), `estimate_status`(AVAILABLE / HOLD), 사용한 집단(`reference_groups`) |
| `result.separate_items[]` | 광고에서 별도 납부로 적은 항목(관리비 안의 합계에 넣지 않음) |
| `result.items.OTHER` | 기타: 광고에 명시된 금액만(없으면 `null`), 설명(`descriptions`) |
| `result.reference_comparison[]` | 광고 금액이 있는 항목의 참고 구간과의 차이(사실 기록, 상태와 무관) |
| `result.errors[]` / `reason_codes` / `missing_fields` / `confirmation_questions` | 서버 환경 오류, 사유, 비어 있는 입력, 사용자에게 물을 질문 |

## 시연 결과 (가상 매물: 관악구 다세대 20㎡, 광고 관리비 9만원에 5항목 포함)

[`backend/examples/machine_preview_demo.md`](examples/machine_preview_demo.md) 참고. 요약:

| 시나리오 | 전기 | 수도 | 가스 | 인터넷 |
|---|---|---|---|---|
| 10월 · 1인 · 개별 도시가스 | 23,930~36,970 | 10,950 | 19,500~38,310 | 17,600~30,000 |
| 1월(겨울) | 24,080~37,340 | 10,950 | 60,040~120,940 | 17,600~30,000 |
| 8월(여름) | 38,020~61,020 | 10,950 | 13,750~26,590 | 17,600~30,000 |
| 10월 · 난방 방식 모름 | 23,930~36,970 | 10,950 | 보류 | 17,600~30,000 |

계절에 따라 가스(겨울)와 전기(여름)가 크게 달라지는 점이 반영됩니다. 값의 근거와 한계는 `machine/docs/maintenance_validation.md`.

## 한계 · 아직 안 한 것

- 개별 가구의 실제 청구액 예측 정확도는 검증하지 않았습니다(실제 고지서 0건).
- 도커 이미지 실행 시험은 하지 않았습니다(`Dockerfile.dockerignore` 허용만 추가).
- 프론트 화면 연결은 없습니다. 이 엔드포인트의 응답을 어떻게 보여 줄지는 프론트와 협의가 필요합니다.
- 기존 `utility-estimates`와 값이 다릅니다(그쪽은 연 평균 ÷ 12 고정 시나리오). 어느 쪽을 서비스에 쓸지는 팀 결정입니다.

## 리포트의 "관리비 참고금액(null)" 해결

`MACHINE_MAINTENANCE_PREVIEW=true`이면 `GET /listings/{id}/report`의 `maintenance_reference_groups`에 머신 참고금액이 채워집니다(꺼져 있으면 기존대로 `REFERENCE_NOT_CONNECTED`, null). 필요한 서울 집계표는 이제 저장소에 들어 있어 별도 파일이 필요 없습니다.

- 사용자 시나리오가 없으므로 기준 월은 매물 기준일(`as_of`)의 달, 가구원 수·난방은 "알 수 없음"으로 둡니다. 그래서 **전기·인터넷은 값이 나오고, 수도(가구원 수 필요)·가스(난방·사용 확인 필요)·기타는 비어 있습니다.** 값을 만들어 채우지 않습니다.
- 가구원 수·난방까지 반영한 값은 `POST /listings/{id}/maintenance-reference`로 받습니다.
- 머신 오류나 파일 누락이면 리포트는 죽지 않고 기존처럼 null(자료 없음)을 돌려줍니다.
