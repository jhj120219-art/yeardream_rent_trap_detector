# 분석 함수 연동 규격 (`analyze.py`)

```python
import analyze
pool = analyze.load_pool()                 # 서버 시작 시 1회 (output/clean_rent_data.csv, 약 30만 행)
result = analyze.analyze_listing(payload, pool)   # JSON 직렬화 가능한 dict
```

## 입력 payload
| 필드 | 필수 | 설명 |
|---|---|---|
| district_code | 예 | 자치구 코드(관악 11620, 광진 11215, 마포 11440, 동작 11590, 강서 11500, 노원 11350). `gu_name`도 허용 |
| legal_dong_code 또는 dong | 예 | 10자리 법정동 코드(데이터로 동 이름 변환) 또는 동 이름 |
| building_type | 예 | APARTMENT / MULTI_UNIT(연립다세대) / DETACHED_MULTI(단독·다가구) / OFFICETEL (한글 용도명도 허용) |
| area_m2, area_basis | 예 | 면적과 기준: EXCLUSIVE(전용) / SUPPLY / RENTAL_REPORTED / UNKNOWN |
| deposit_10k_krw, rent_10k_krw | 예 | 보증금·월세(만원) |
| built_year, floor | 아니오 | 층 0 또는 없음 = 층 미확인, 음수 = 지하 |
| as_of | 아니오 | 기본: 데이터 최신일 + 1 |

## 출력
| 필드 | 값 |
|---|---|
| status | COMPARED / REFERENCE_ONLY / INSUFFICIENT_DATA / INPUT_REVIEW_REQUIRED / OUT_OF_SCOPE |
| price_label | UPPER_TAIL(상위 10% 초과) / UPPER_RANGE(상위 25% 초과) / TYPICAL_RANGE / LOWER_RANGE(하위 25%) / UNRATED(판정 안 함) |
| stage, sample_count | 탐색 단계(1~3), 비교 거래 건수 |
| confidence_grade | HIGH / MEDIUM / LOW / NONE |
| prices_10k_krw | q10, q25, median, q75, q90 (만원) |
| rent_difference_10k_krw, rent_difference_pct, percentile | 입력 월세와 비교 중앙값의 차이, 백분위 |
| warnings, warning_texts | 경고 코드와 사용자 문구 |
| messages | 화면 표시용 한국어 문장 |
| hold_reasons | 판정을 보류한 이유(area_unverified, floor_unknown, stage3, low_confidence 등) |
| errors | INPUT_REVIEW_REQUIRED 일 때 수정할 항목 |
| data_source, data_as_of | 데이터 출처와 최신 계약일 |

## 판정 규칙 요약
- UPPER_TAIL 은 신뢰도 HIGH 일 때만. MEDIUM 이면 UPPER_RANGE 까지.
- 다음은 REFERENCE_ONLY + UNRATED(가격 범위는 제공): 입력 면적이 공급·계약면적인 경우, 단독다가구(계약면적 기준이라 전용면적과 같다고 보증 불가 + 층 미확인), 3차(같은 구 전체) 확대, 신뢰도 LOW. 아파트·연립다세대·오피스텔은 서울시 면적이 국토부 전용면적과 건별 대조로 확인되어 면적 때문에 보류하지 않음.
- 사용자 문구에는 "함정·사기·불법·바가지"를 쓰지 않는다(테스트로 검사).
- 정책 스위치: `analyze.POLICY`, 면적 기준 확인 용도: `analyze.AREA_BASIS_VERIFIED`.

## 판정이 나가는 비율 (백테스트 8,995건 기준)
- 면적 기준 확인 반영 후: **44.0%**가 COMPARED 가능(아파트·연립다세대·오피스텔, 1·2차·신뢰도 보통 이상). 단독다가구까지 허용하면 80.7%(층 미확인 경고만 유지) — 정책 결정 대기.
