> **최신 팀 동기화:** 작업 중 PR #1이 팀 main에 병합됐습니다(27e86ad). main을 fast-forward한 뒤 기존 시연 미리보기와 새 저장 API를 통합했습니다. 검토한 분석 브랜치를 임의로 통째로 병합한 것이 아닙니다.

# 분석가 관리비 참고값 저장 API

서비스: 월세구멍 / 마음에 든 집, 놓친 건 없을까?

## 적용 범위

월세 분석·입출력은 유지한다. 이 기능은 서울 유사 가구의 항목별 참고값을 별도로 계산·저장한다. 실제 3건 검증과 방식 선택은 미확인이다. 정상 관리비·개별 고지서 예측·사기 판정으로 사용하지 않는다. 운영에서는 기본 비활성화이며 기존 MAINTENANCE_ENABLED 보류 설정도 우선 적용된다.

- MACHINE_MAINTENANCE_ENABLED=true: 새 API 기능 설정. 기본 false.
- MAINTENANCE_ENABLED=true도 필요. 보류 중에는 새 POST/GET도 503.
- MAINTENANCE_MACHINE_ROOT: 검토한 분석 코드의 machine 디렉터리 절대 경로. 기본 프로젝트 machine. 별도 검토 복사본을 지정할 수 있으며 자동 브랜치 병합 없음.
- ENERGY_REFERENCE_CSV: 분석 코드가 사용하는 기준 CSV를 다른 경로로 지정할 때 사용. 키·환경파일·CSV를 Git에 추가하지 않음.

## 요청 순서

공유 서버 모든 요청에 X-Team-Key, 세션 이후 Authorization: Bearer 토큰을 사용한다.

1. POST /sessions
2. POST /listings: CHECKBOX_TOTAL_V1, 5항목 체크+총액, 사용자 확인 완료. 미체크는 UNKNOWN.
3. 기존 POST /listings/{id}/analyses: 월세 분석은 기존대로 별도 수행.
4. POST /listings/{id}/maintenance-references: 아래 조건과 참고 한계 확인을 보낸다. 선택적으로 Idempotency-Key 사용 가능.
5. GET /maintenance-references/{reference_id} 또는 GET /listings/{id}/report에서 저장 결과 조회.

```json
{
  "target_month": 10,
  "household_size": null,
  "heating_type": "모름",
  "gas_user": "모름",
  "metering": "UNKNOWN",
  "acknowledge_reference_limits": true
}
```

가구원 수·난방·계량 조건을 임의로 채우지 않는다. 면적은 확인된 매물의 전용면적만 사용한다. 입력 확인 전·유효하지 않은 매물·한계 확인 없음·기존 입력·서울 외 지역은 422, 다른 사용자 자료는 404, 코드·CSV·계약 오류나 실행 30초 초과는 상세 비밀 없이 503이며 결과를 저장하지 않는다.

## 결과와 저장

objects의 machine_reference 종류로 기존 매물 하위에 저장한다. 스키마 변경 없음. 입력 조건, 분석 원본 result, 체크/미체크 groups, 출처·통계 연도·요금표 버전·원 단위 메타데이터를 함께 보존한다. report.machine_maintenance_reference는 마지막 저장 결과이며 읽을 때 재계산하지 않는다. 활성화 상태에서는 저장 groups를 maintenance_reference_groups에 표시한다.

- 고객 광고 총액은 만원, 참고 범위와 합계는 원. 두 단위를 혼동하거나 차액을 기타로 만들지 않는다.
- OTHER는 분석 참고 범위를 만들지 않으며 누락 항목을 명시한다. 묶음에서 하나라도 자료가 없으면 완성 합계는 null.
- null은 자료 없음, 실제 명시된 0은 무료. 미체크 UNKNOWN을 별도 청구 확정으로 바꾸지 않는다.
- 출처별 적용 조건과 가정은 result.conditions_used / assumptions / utility_estimates 등 원본과 provenance에 보존한다. 2023 에너지 통계, 코드의 요금표 버전, 서울 범위와 집단 사용량의 계절 배분 가정을 함께 검토해야 한다.
- 분석 모듈은 별도 프로세스로 실행해 분석 코드의 sys.path 변경이 기존 월세 엔진에 영향을 주지 않게 한다. 동일 재시도는 저장 객체 재사용, 다른 입력의 동일 재시도 키는 409.

## 이번 검증

실제 PR e8216f0의 분석 코드·1,012행 CSV를 Git 제외된 격리 복사본에서 사용했다. 시험 매물은 합성 자료이며 실제 3건 정확도 검증과 다르다. 전체 회귀 216개 통과 후 추가한 HTTP 프로세스 재시작 시험을 포함해 새 기능 시험 7개 통과(SQLite·별도 MySQL). 확인 전 차단·소유자 격리·재시도·기타 미생성·불완전 합계·저장·조회·프로세스 재시작 유지 확인.

## 최종 통합 시험

PR #1 병합 후 최신 팀 main과 미리보기·저장 API를 통합한 최종 전체 시험은 226 passed, 경고 1개입니다. SQLite와 격리 MySQL, 실제 새 기준 CSV를 사용했고 실제 HTTP 프로세스 재시작도 포함합니다.
