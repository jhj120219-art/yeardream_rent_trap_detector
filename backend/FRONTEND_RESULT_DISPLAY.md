# 월세 결과 표시 연결 — 2026-10-22

## 이번에 확인한 팀 상태

확인 기준 main 0c2bd7e. GitHub API로 전체 5개 브랜치·열린 PR 0개 확인. 직전 점검 후 새 커밋 없음. 분석 최신 파일은 기준 CSV와 관리비 함수·변환·요금표·문서를 제공함. 실제 3건 검증 결과와 미체크 참고값 출력 보완은 아직 확인되지 않음.

frontend/frontend-design의 HTML·사용흐름 문서는 v0.5 시안이며 connect-src 'none', 가상 값·가상 추출·메모리 상태를 사용함. 실제 API·DB 연결이 아님. 총액만 입력·예상 공과금 합계 설계는 이후 미팅의 5항목 체크+총액·체크/미체크 표시와 차이가 있으므로 프론트 담당 업데이트가 필요함. 프론트 원본은 수정하지 않음.

## 새 백엔드 응답

GET /listings/{id}/report → `rent.presentation` (RENT_DISPLAY_V1)을 추가했다. 기존 `rent.result`·`rent.state`·분석 저장값은 그대로다. 새 값을 보여주기 위해 분석 재실행은 필요 없다. 저장된 분석이 없다면 NOT_ANALYZED다.

| 필드 | 프론트 사용법 |
|---|---|
| status_label / state | 비교 완료·참고용·자료 부족·입력 확인 필요·지원 범위 밖·분석 전 |
| headline | 소비자가 바로 읽을 한 문장. 예: 비교 기준보다 월 10만원 · 16.67% 높아요 |
| input_rent_10k_krw | 고객이 입력한 월세(만원) |
| reference_rent_10k_krw | 비교 중앙값(만원), 없으면 null |
| difference_10k_krw | 분석에서 받은 차액(만원), 관리비 제외 |
| difference_percent | 분석 비율 ×100으로 변환한 퍼센트. **프론트에서 다시 ×100하지 않음** |
| percent_basis | COMPARABLE_MEDIAN: 퍼센트의 분모는 비교 중앙값 |
| middle_50_percent_10k_krw | 유효한 Q25~Q75 구간, 없으면 null |
| can_show_direction / direction / tone | true일 때 HIGHER/RED, LOWER/BLUE, SAME/NEUTRAL. 색과 문구를 함께 표시 |
| reason_codes / notice | 보류·누락 사유·관리비 제외 및 분석 한계 |

참고용·자치구 확대·UNRATED에서는 can_show_direction=false, NEUTRAL. 원본이 COMPARED여도 실제 scope_code=DISTRICT 또는 stage=3이면 프론트 문서의 판정 금지 규칙에 따라 표시만 REFERENCE_ONLY로 제한한다. 원본 정책을 수정하거나 가격을 재계산한 것이 아니다. 화면 상태·색상은 presentation을 쓰고 분석 근거와 원래 라벨은 rent.result에서 확인한다.

입력 미확인·잘못된 입력·지원 범위 밖·자료 부족에서는 이전 숫자를 결론으로 노출하지 않는다. 차액·차이율 누락은 0으로 채우지 않는다. 두 값의 방향이 모순되면 색상·방향 문구를 보류하고 확인 사유를 표시한다.

## 프론트에 요청

1. 실제 API 연결용 브랜치/배포 주소를 특정해달라. 오프라인 시안의 connect-src none을 유지한 채 연결됐다고 보지 않는다.
2. 미팅 기준 5항목 체크+총액 입력과 report.maintenance_reference_groups를 연결한다. 미체크는 별도 청구 확정이 아니다.
3. 월세 결과는 rent.presentation의 차액·퍼센트·색상·문구를 연결한다. 자료 부족·미확인·참고용·통신 실패 화면도 실제로 확인한다.
4. 원문 key/token·접속키는 화면·저장소에 넣지 않고 오류 공유 시 상태·동작·요청 ID만 남긴다.

## 분석에 요청 — 이미 있는 함수 설명을 다시 묻지 않음

- 현재 코드에서 체크 WATER/INTERNET/OTHER인 경우 WATER/INTERNET 참고값만 반환돼 미체크 ELECTRICITY/GAS가 빠지는 실행을 확인했다. 고객 선택을 변경하지 않고 계산 가능한 항목의 참고값·보류 사유를 별도 반환하는 출력 확장이 필요하다. 임의 포함 처리·추정값 생성으로 우회하지 않았다.
- 강서2·송파1 실제값·방식별 산정값·오차·선택 결과·적용 조건이 필요하다. K-apt 60단지 시험과 별개다.
- OTHER 근거가 없으면 미제공 유지. 운영 기능은 실제 검증 전 계속 꺼둔다.

집 서버 적용·실제 프론트 통합·관리비 정확도 검증은 별도이며 이번 표시 응답 개발 완료와 구분한다.
