> **v1.1 변경점(분석 담당):** building_type 별칭 SINGLE_MULTI_HOUSEHOLD→DETACHED_MULTI, area_basis에 CONTRACT 추가, 면적 일괄 보류 삭제, 층 필드 분리(floor_type/floor_source 등), 입력을 listing/options/confirmation으로 분리, 층 테스트 F01~F12 추가. 원본 준비팩은 ChatGPT가 작성한 초안이며 이 폴더가 최신 규칙에 맞춘 버전입니다.

# AI 월세 함정 탐지기 | 주소·이미지 입력 연동 준비팩 v1.1 (MVP)

이 팩은 실서비스 구현 완료본이 아니라 **팀 간 인터페이스 규격, 프롬프트, 수동 QA 템플릿**입니다.

## 권장 입력 흐름

1. 주소 입력: 주소 검색 API → 사용자 선택/확정 → 법정동 코드/지역 및 주소 정규화 → 사용자가 월세·보증금·면적 추가 입력
2. 이미지 입력: 사용자 캡처 → Vision API → `image_extraction_example.json` 구조 → 원문 근거와 함께 폼 미리 채움 → 사용자 확인/수정
3. 두 경로를 계약 v1.1(`contract/analysis_contract_v1.1.json`, 예시 `contract/examples/`)의 `listing/options/confirmation` 형식으로 통합 → `normalize_listing()` → `analyze_listing()` 호출
4. 비교 함수는 `COMPARED`/`REFERENCE_ONLY`/`INPUT_REVIEW_REQUIRED`/`INSUFFICIENT_DATA`/`OUT_OF_SCOPE` 등 명시적 상태로 반환

## 필수 원칙

- OCR·멀티모달 AI가 미기재 정보를 지어내지 않게 한다. 누락/모호 = `null` 또는 `UNKNOWN`.
- AI가 추출한 값은 **절대 곧바로 시세 판정에 넣지 않는다**. 화면에서 사용자 확인·수정 과정을 둔다.
- 주소만으로 매물의 현재 보증금·월세·관리비·인터넷 포함 여부를 알아낼 수 없다.
- 전용/공급/계약면적은 구분한다. 서울시 `RENT_AREA`는 국토부 CSV 건별 대조로 **아파트·연립다세대·오피스텔=전용면적, 단독다가구=계약면적**임을 확인했다(v1.1에서 '일괄 보류' 규칙 삭제). 공급면적(SUPPLY)이 입력되면 해당 매물만 가격 판정 보류.
- 사용자 광고의 `4층`은 '건물 4층' 또는 '해당 호실 4층'일 수 있다. 증거가 없다면 `floor`는 null.
- '인터넷 가능'은 '인터넷 비용 포함'이 아니다. 시설이 표시되지 않으면 `UNKNOWN`으로 표시.
- `floor=0`은 단독다가구에서 확인된 지상층이 아니다. 층 미확인은 `null`.
- **v1.1 층 규칙:** 매물 층(`floor`)·건물 전체 층(`total_floors`)·지상/지하(`floor_type`)·출처(`floor_source`)·원문(`floor_raw_text`)을 분리한다. 단독다가구는 사용자가 확인한 지상층(`floor_type=GROUND`, `USER_CONFIRMED`)일 때만 가격 판정이 나가고, 반지하·층 미확인은 가격 범위만 제공한다. AI가 읽은 층(IMAGE_EXTRACTED)은 사용자 확인 전까지 판정 근거가 아니다.
- 주소 정규화 결과 법정동/행정동 혼동 방지. `CGG_CD`·`STDG_CD`는 실제 데이터 사전과 대조해 매핑.
- 정확도 검증 시 값 정답률뿐 아니라 누락/미기재를 과감히 UNKNOWN으로 두는지 검사.
- 전화번호, 임대인 이름, 연락처, 상세 호수 등 개인정보는 가능한 업로드 전에 가리거나 즉시 폐기한다.
- 광고 수집은 약관·저작권/재배포 조건을 확인하며, 테스트 표본은 사용 허락을 받아 보관.

## 팀별 연결

| 담당 | 입력 | 출력/책임 |
|---|---|---|
| AI 광고 분석 | 이미지 | 항목별 value/raw_text/review_required, 추출 상태 |
| 프론트 | AI 결과·주소 조회 결과 | 사용자 수정 가능한 폼, 미확인 표시, 최종 확인 입력 |
| 백엔드 | 확인 완료 매물 | 서버 검사, 주소·법정동 코드 정규화, 데이터 분석 함수 전달 |
| 데이터 분석 | 확인 완료 값, 2025~26 실거래 비교 풀 | 유사 거래 1~3차 탐색, 가격 범위, 신뢰도, 보류 사유 |

## 검증표

`extraction_test_template.csv`에는 실제/동의받은 이미지 30장을 넣고 정답 컬럼을 기록하세요. 정확도는 최소 필드별로 확인합니다.

- **필수 금액 필드 정확 일치**: 보증금과 월세의 `만원` 단위 값 일치 여부
- **면적 일치 + 기준 분류**: 숫자와 단위/전용·공급·불명 정확성
- **옵션 상태 정확도**: 포함/별도/없음/미확인의 혼동
- **거짓 채움(hallucination)**: 광고에 없는 값을 채워 넣었는지
- **자동입력 후 수정률**: 사용자가 몇 개 필드를 수정해야 했는지
- **파이프라인 성공률**: API 오류, 2개 매물 혼재, 주소 누락 처리 등

## 추천 기술

- 1주일 MVP: 이미지 인식 가능 LLM API(OpenAI/Gemini 중 1개) + 구조화 출력(JSON Schema) + 주소 검색 API(카카오 Local 또는 행정안전부 검색 API)
- OCR 백업 후보: PaddleOCR 한국어 PP-OCRv5, EasyOCR, NAVER CLOVA OCR(유료 서비스)
- 파인튜닝은 우선 제외: 한국어 광고 캡처 20~30장 정도의 수동 평가를 먼저 실시하고 미달 항목만 프롬프트/규칙 보완

## 공개 문서

- OpenAI vision: https://developers.openai.com/api/docs/guides/images-vision
- OpenAI JSON: https://developers.openai.com/api/docs/guides/structured-outputs
- Google Gemini vision: https://ai.google.dev/gemini-api/docs/image-understanding
- Google Gemini JSON: https://ai.google.dev/gemini-api/docs/structured-output
- PaddleOCR: https://github.com/PaddlePaddle/PaddleOCR
- EasyOCR: https://github.com/JaidedAI/EasyOCR
- CLOVA OCR: https://api.ncloud-docs.com/docs/ai-application-service-ocr
- Kakao Local: https://developers.kakao.com/docs/ko/local/dev-guide
- 행정안전부 주소: https://www.data.go.kr/data/15057017/openapi.do
