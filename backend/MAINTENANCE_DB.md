> **2026-10-21 논의 중:** 관리비 기본안은 전기·수도·가스·인터넷·기타 5항목입니다. 아파트의 청소·공용관리비를 별도 항목으로 추가할지, 모든 주택유형에서 기타로 통일할지는 미확정입니다. 결정 전 현재 FIVE_ITEMS_V1 구현을 유지하고 DB·API 항목을 임의로 늘리거나 기존 세부내역을 삭제하지 않습니다.

> **최신 5항목 규격(2026-10-21):** 현재 구현은 전기·수도·가스·인터넷·기타 관리비 5항목입니다. 신규 저장은 총액 1행+항목 5행, 과거 7행은 삭제하지 않고 호환 조회합니다. [프론트 필드·기존 자료 처리](ADVERTISED_COSTS.md). 아래 과거 7항목 설명보다 이 규격이 우선하며, 집 실행 서버 적용은 별도 확인해야 합니다.

# 관리비 출력 JSON → 항목별 MySQL 저장

2026-10-20. 원본 `objects.payload`의 매물 입력은 보존하고, 프론트 출력 `report.advertised_costs`에 맞춰 컬럼/행으로 분리했다. POST/GET 규격은 유지한다. 광고에 적힌 사실을 저장하는 변경이며 관리비 평균·추정·적정성 비교 기능을 켜지 않는다.

| 테이블 | 한 행의 의미 | 주요 컬럼 |
|---|---|---|
| listing_maintenance | 매물 1개의 광고 관리비 | listing_id(PK/FK), amount_10k_krw, user_confirmed, note |
| listing_maintenance_items | 매물 1개의 비용 항목 1개 | listing_id+item(PK), status, raw_status, amount_10k_krw, label |

항목은 ELECTRICITY/WATER/GAS/INTERNET/CLEANING/COMMON/OTHER의 7개다. 포함 여부는 INCLUDED/SEPARATE_CHARGE/UNKNOWN, 미기재 금액은 null, 광고에 실제 무료로 적힌 값만 0이다. 기타 항목명은 label에 저장한다. 인터넷 AVAILABLE은 포함을 뜻하지 않아 status는 UNKNOWN이며 raw_status에는 AVAILABLE을 보존한다.

금액 단위는 **만원**이다. 기존 API의 유한 실수 표현과 호환되도록 MySQL DOUBLE / SQLite REAL로 저장하고, 원문·정밀 표기는 기존 JSON에 보존한다. 항목 금액을 관리비 총액에 다시 더하지 않고 월세 분석에도 반영하지 않는다.

## 저장·조회·삭제

- 새 매물의 JSON·총액 행·7개 항목 행은 한 트랜잭션으로 커밋한다. 중간 오류는 원본 입력까지 함께 롤백한다. 기존 Idempotency-Key 재시도는 같은 매물을 반환하므로 행이 중복 생성되지 않는다.
- 결과 보고서의 advertised_costs는 정규화 행에서 조합한다. 원본 매물 GET의 input.options는 기존 JSON 그대로다. 보존된 예전 매물에 아직 정규화 행이 없으면 기존 출력 방식을 유지한다.
- 관리비 조회는 objects와 결합해 소유자를 확인한다. 매물·세션 삭제 시 FK cascade로 총액/항목이 함께 삭제된다.
- 입력 수정은 기존 규칙대로 새 매물+previous_listing_id로 보존한다. 과거 관리비 행을 덮어쓰지 않는다.

## 기존 데이터 적용

1. API를 중지하고 DB를 백업한다.
2. 별도의 스키마 관리자 계정으로 init_mysql을 실행해 두 테이블을 추가한다. 런타임 앱 계정의 SELECT/INSERT/DELETE 권한은 유지한다.
3. 앱용 DATABASE_URL 환경에서 `python -m backend.scripts.backfill_maintenance --offline-confirmed`를 실행한다.
4. backfill은 원본 JSON과 분리 행의 출력이 일치하는지 전체 대조한다. 이미 같은 행은 중복 생성하지 않고, 값이 다르면 덮어쓰지 않고 트랜잭션을 실패시킨다.
5. /ready는 추가된 두 테이블의 접근도 확인한다. API를 다시 시작한 뒤 저장/보고서를 검사한다.

기존 SQLite→MySQL 마이그레이션도 원본 JSON에서 두 테이블을 같은 대상 INSERT 트랜잭션 안에서 재구성한다. 사용자 입력·세션·분석 원본을 삭제하거나 예시 응답으로 교체하지 않는다.

## 이번에 실제 분리한 출력 데이터

입력: `backend/examples/api_responses.json`, `backend/examples/utility_estimates.json`.

두 파일의 synthetic 표식을 확인하고 **별도 rent_examples DB**에 적재했다. 팀/실사용 DB와 분리한다. 원본 출력 파일 전체와 파일명·SHA256은 synthetic_import_source 객체로 보존한다. 출력에 연결된 입력 사례 **8건 → 관리비 총액 8행 + 항목 56행**이다. 공과금 추정 결과 숫자를 실제 청구액이나 광고 명시 금액으로 섞어 넣지 않는다. 단위가 원인 공과금 출력도 임의로 만원 입력에 복사하지 않는다.

재현 명령은 빈 rent_examples 전용 DB의 DATABASE_URL을 설정한 뒤 다음과 같다. 스키마는 별도 관리자 도구로 먼저 만든다. import는 원본 출력이 합성 예시임을 명시하지 않거나, DB명이 rent_examples로 시작하지 않거나, 이미 데이터가 있으면 거부한다.

```powershell
python -m backend.scripts.import_maintenance_examples --input backend/examples/api_responses.json --input backend/examples/utility_estimates.json
```

직접 SQL로 항목을 확인할 수 있다. 아래는 샘플 DB에서만 실행한다.

```sql
SELECT listing_id, amount_10k_krw, user_confirmed, note
FROM rent_examples.listing_maintenance;
SELECT listing_id, item, status, raw_status, amount_10k_krw, label
FROM rent_examples.listing_maintenance_items
ORDER BY listing_id, item;
```

실제 팀 DB의 기존 사용자 매물은 적용 시점에 0건이었다. 예시 8건을 팀 사용자 매물로 넣은 것이 아니며 새 실제 입력부터 자동으로 항목별 저장된다. DB 비밀번호·키·원본 데이터 파일·SQL 백업은 Git 제외다.


## 2026-10-21 실제 서버 재검증

공개 HTTPS API로 확인용 매물을 등록한 뒤 실제 MySQL의 `listing_maintenance_items` 7행과 보고서 `advertised_costs`가 일치하는지 확인했다. 수도 명시 금액 1만원, 청소 명시 금액 0원, 전기 미입력 null 구분과 원본 JSON 보존을 통과했다. 검사 세션과 그에 연결된 매물·관리비 행만 삭제했다.

검사 정리 후 팀 DB는 총액 0행·항목 0행이었다. 이는 현재 실사용 매물이 없다는 뜻이며 테이블 누락이 아니다. 별도 합성 예시 DB는 총액 8행·항목 56행이다. 실제 관리비 정확도 근거로 사용하지 않는다.

이 분리는 광고 입력 저장용이다. 동일 주소 1/n 배분·유사 매물 관리비 추정은 분석 기준과 실제 데이터 검증 전이므로 구현·활성화하지 않았다. 관리비 계산 응답은 계속 ON_HOLD다.
