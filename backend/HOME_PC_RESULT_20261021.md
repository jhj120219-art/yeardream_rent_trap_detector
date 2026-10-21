# 집 PC 적용 결과 — 2026-10-21

## 동기화와 적용

개인 main을 매장 최종 c34ecac으로 fast-forward했다. 미커밋 변경은 없었다. 바탕화면 개인 사본도 동기화했으며 기존 미추적 output/을 보존했다. 현재 가동 소스는 OneDrive 작업 폴더다. 적용 대상 AGENTS.md는 없었다. 분석·프론트·최상위 파일은 수정하지 않았다.

기존 보호 runtime은 C:/Users/wlsdu/AppData/Local/YeardreamRentBackend, DB runtime은 C:/Users/wlsdu/AppData/Local/YeardreamRentMySQL이다. Windows 앱 환경에서 연결 정보의 key_file 실제 경로가 다를 수 있으므로 connection.json을 우선 읽는다. 시작/종료는 runtime의 server-start.cmd/server-stop.cmd다. MySQL 8.4.11은 loopback 3307만 사용한다. 기존 Python 3.13과 backend/.venv/vendor를 유지했다. 새 PC 환경·CSV·비밀정보가 Git으로 전달됐다고 가정하지 않았다.

## 백업·데이터 보존

DB 변경 전 앱·팀 MySQL SQL 백업을 만들었다. 새 verify_local_mysql_backup 도구로 매번 새로운 rent_restore_check_* DB에 복원하고 sessions/objects/object_links/listing_maintenance/listing_maintenance_items 전체 행 값을 대조했다. 앱과 팀 모두 일치했으며 검사 DB와 임시 client 설정만 삭제했다. 기존 운영 DB는 복원 대상으로 사용하지 않았다. 원본과 같은 디스크 백업이며 외부 재난 복구까지 검증한 것은 아니다.

팀 DB 변경 전과 시험 정리 후: sessions 4, objects listing 4 / analysis 4 / request_receipt 8, object_links 0, 관리비 총액 4행, 항목 28행. 기존 매물 4건은 각각 과거 7항목 기록이다. 모두 5항목 호환 조회를 통과했으며 기존 행을 삭제·재구성하지 않았다. 보호 폴더에 저장한 전체 테이블 지문으로 API 2회 재시작 전후 원본 값 불변을 확인했다.

## 실제 서버 시험

기존 supervisor 시작/종료 방식으로 최신 코드를 적용하고 다시 재시작해 영속성을 확인했다. 최신 주소는 보호 runtime의 connection.json/접속주소.txt를 사용한다. 임시 URL이나 접속키를 저장소에 고정하지 않는다.

- /health 200, /ready 200, /capabilities 200. service=월세구멍, slogan=마음에 든 집, 놓친 건 없을까?, FIVE_ITEMS_ALL_HOUSING_TYPES, CHECKBOX_TOTAL_V1, v2 READY 확인.
- 같은 건물 우선 비활성화 유지. 분석가의 현재 main 월세 코드와 실제 CSV로 동네 비교 COMPARED 및 결과 DB 저장·조회 확인.
- 공개 HTTPS로 5개 체크 상태+관리비 총액 7만원/null/0 입력. INCLUDED/UNKNOWN 유지, 항목 금액은 모두 null, 총액 null과 실제 0 구분.
- 체크 WATER/INTERNET, 미체크 ELECTRICITY/GAS/OTHER 구분. 분석 참고값은 REFERENCE_NOT_CONNECTED/null, 누락 항목과 미완성 묶음 합계 null 확인. 미체크를 별도 청구 확정으로 바꾸지 않음.
- 확인 전 분석은 계약대로 INPUT_REVIEW_REQUIRED이며 가격을 계산하지 않음(HTTP 201 검토 결과 저장 방식은 유지).
- 임시 세션 2개·매물 4개·분석/검토 결과 2개 생성 시 총액 8행·항목 48행(기존 28+신규 20). 서버 재시작 후 동일 토큰·결과·행 수 유지, 다른 세션 조회 404 확인.
- 시험 세션만 삭제한 뒤 위 기존 집계·전체 값 지문으로 복귀. 실제 사용자 4개 세션은 삭제하지 않음.
- 공개 프론트 origin CORS, 미승인 origin 차단, 키 누락 401, 재시도 중복 방지 통과. 요청 ID 응답·로그 기능도 재시작으로 적용됨.

현재 수행: 개인 사본 전용 MySQL 전체 회귀 검사 206 passed + 새 복원 안전장치 검사 5 passed. 팀 최종 사본 전체 회귀 검사 211 passed, 클라이언트 Node 검사 5 passed. Starlette/httpx 폐기 예정 경고 1건이 전체 Python 검사에서 남는다. 과거 매장 검사 수를 재사용하지 않았다. 실제 화면 클릭·디자인 검증은 수행하지 않았다.

재현 도구: backend/tests/smoke_home_checkbox.py prepare/resume. prepare 후 서버를 재시작하고 resume으로 재조회·정리한다. 토큰·시험 ID는 runtime의 비공개 임시 파일에만 저장하며 Git에 넣지 않는다. 실제 사용자 사용 중 행 수가 변하면 검사를 무시하지 않고 실패로 처리한다.

## 분석 연결 차단과 확인한 PR

팀 main 7af8fab, PR #1 OPEN / chore/machine-final HEAD f08cad0e9381c99937e7e75e4c83dcedc473afc5 확인. PR 전체를 merge하지 않았다.

실제 관리비 진입점은 machine.analysis_internal.utility.integration.run_maintenance(payload)다. backend_options+contract_version FIVE_ITEMS_V1과 target_month/household_size/housing_type/area_m2 또는 area_band/heating_type/gas_user, 사용자 확인·계량 조건을 사용한다. PR의 backend/app/machine_maintenance.py는 기본 꺼짐 시연 미리보기이며 결과를 DB에 저장하지 않는다. 현재 CHECKBOX_TOTAL_V1 그룹 계약과 별도이고 운영 저장·조회 연결을 완료한 것이 아니다.

필수 energy_reference_2023.csv는 작업 폴더·바탕화면·OneDrive 문서·Downloads 검색과 다운로드 ZIP 2개 내부에서 찾지 못했다. ENERGY_REFERENCE_CSV 환경변수도 없었다. PR CSV 원본도 없다. 파일은 다음 경로 중 하나 또는 비공개 ENERGY_REFERENCE_CSV로 공급해야 한다.

- machine/data/utility_stats/energy_reference_2023.csv
- machine/analysis_internal/utility/reference_data/energy_reference_2023.csv

코드에 이미 있는 준비 방법: KESIS 가구에너지패널조사 14차(2023) 결과표를 자료사용목적 등록 후 받아 엑셀 4개를 machine/data/utility_stats/keei/hep14/에 놓고, PR의 parse_hep14.py를 실행한다. CSV 필수 열은 table,sheet,region,category,item,unit,estimate,rse_pct다. 재배포 이용 조건 확인이 필요하다. 파일을 받기 전 다른 통계나 예시 숫자로 대체하지 않았다.

PR의 명시 단위: 입력 광고 총액은 만원, 반환 reference_low/high_krw는 원. 사용량 출처는 2023 서울 패널, 2026 요율로 환산한 참고 금액이며 서로 다른 집단 평균의 최소~최대다. 개별 고지서 예측·정상가격 범위가 아니다. 실제 수치·지원 지역/유형/계절 조건은 파일 미연결로 재현 검증하지 못했다. OTHER는 광고 명시 정보만 사용하고 총액 역산은 기본 비활성화다.

PR docs/maintenance_validation.md의 60개 서울 아파트 단지 평균 시험은 읽었으나, 이번 미팅의 강서 2건·송파 1건 익명 실제 자료·방식별 오차·선택 결과는 발견되지 않았다. 해당 3건에 대한 선택 완료나 전체 정확도를 주장하지 않는다. 분석 담당에게 필요한 것은 이미 있는 함수 설명이 아니라 이용 가능한 CSV와 3건 검증 결과·선택 근거·적용 조건, OTHER의 자료 유무다.

## 프론트 전달 초안 — 직접 발송하지 않음

집 서버에 월세구멍과 5항목 체크+총액을 적용했고 실제 저장→월세 분석→보고서 조회 및 재시작 유지 검증을 마쳤습니다. 최신 주소는 비공개 실행 정보에서 확인하고 접속키는 별도로 전달하겠습니다. 월세 비교·관리비 체크 입력/저장·체크/미체크 결과·자료 없음·사용자 확인·통신 실패/재시도를 테스트해주세요. 관리비 분석 참고금액은 CSV와 검증 결과 미연결로 아직 자료 없음(null)입니다. 항목별 금액 입력, 미체크=별도청구, 빈값=0 처리는 하지 말아주세요.

요청 순서: X-Team-Key로 POST /sessions → Bearer 토큰과 같은 키로 GET /capabilities,/locations → 확인한 CHECKBOX_TOTAL_V1 입력 POST /listings → POST /listings/{id}/analyses → GET /listings/{id}/report. 응답 service / advertised_costs / maintenance_reference_groups / rent.result 사용. 오류는 키·토큰 없이 X-Request-ID·상태·동작만 공유한다.

## 원격 관리·남은 사용자 작업

집PC_원격설정.zip과 C:/ProgramData/YeardreamRentRemote/yeardream-home-connection.json을 찾지 못했다. 이 환경에서는 sshd/Tailscale 서비스도 확인되지 않았다. 새 키 생성·원격 접속 설정·인터넷 MySQL 공개는 하지 않았다.

사용자 작업: 매장의 원격 설정 ZIP을 집 PC로 별도 전달. 내용을 확인한 뒤 인계서대로 관리자 허용 및 동일 Tailscale 계정 로그인 필요. ZIP 없이 연결 완료로 보고하지 않는다. 분석 담당은 CSV와 3건 검증 결과를 별도로 전달해야 한다.
