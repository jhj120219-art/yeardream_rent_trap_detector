# -*- coding: utf-8 -*-
"""최근 공공데이터(공공데이터포털, 이용허락범위 제한 없음)를 내려받아 서울 요약 JSON 으로 만든다.
- 한국전력공사_주택용 계약전력 구간별 현황 (15119479): 2025 월별, 시도 x 계약전력구간 -> 서울 1~3kW 구간 고객당 사용량·판매수입
- 한국가스공사_월별 가구당 도시가스 소비량 (15156658): 2014~2024 월별 서울 m3/수요가
요약 결과(recent_data/recent_seoul_summary.json)는 공공데이터 집계라 저장소에 포함할 수 있다. 원본 CSV 는 data/utility_stats/recent/ 에 둔다.
사용: python -m utility.recent_load  (analysis_internal 폴더에서)  /  --offline 이면 내려받기 없이 저장된 CSV 로 다시 요약
"""
import csv
import io
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RAW_DIR = ROOT / 'data' / 'utility_stats' / 'recent'
OUT = HERE / 'recent_data' / 'recent_seoul_summary.json'
DATASETS = {'15156658': 'gas_per_household', '15119479': 'elec_by_contract_power'}
PAGE = 'https://www.data.go.kr/data/{id}/fileData.do'
UA = {'User-Agent': 'Mozilla/5.0'}


def _get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def download(ds_id):
    html = _get(PAGE.format(id=ds_id)).decode('utf-8', 'replace')
    m = re.search(r'"contentUrl":\s*"([^"]+)"', html)
    if not m:
        raise RuntimeError(f'{ds_id}: 다운로드 주소를 찾지 못함(페이지 구조 변경?)')
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f'raw_{ds_id}.csv'
    path.write_bytes(_get(m.group(1)))
    return path


def _rows(path):
    return list(csv.DictReader(io.StringIO(path.read_bytes().decode('cp949'))))


def summarize_gas(rows):
    out = {}
    for r in rows:
        ym = r['연월'][:7]
        out[ym] = float(r['서울'])
    years = {}
    for ym, v in out.items():
        years.setdefault(ym[:4], []).append(v)
    return dict(monthly_m3_per_household=out, annual_m3_per_household={y: round(sum(v), 1) for y, v in years.items() if len(v) == 12})


def summarize_elec(rows):
    seoul = [r for r in rows if r['시도'].startswith('서울')]
    by_month = {}
    for r in seoul:
        by_month.setdefault(r['조회기간'], []).append(r)
    monthly = {}
    for ym, rs in sorted(by_month.items()):
        seg = next((r for r in rs if r['계약전력구간'].replace(' ', '') == '1~3'), None)
        tot_c = sum(float(r['고객호수']) for r in rs if r['고객호수'])
        if not seg or not seg['고객호수'] or not seg['판매량']:
            continue
        c, k, w = float(seg['고객호수']), float(seg['판매량']), float(seg['판매수입'])
        monthly[ym] = dict(customers=int(c), kwh_per_customer=round(k / c, 1), won_per_customer=round(w / c), won_per_kwh=round(w / k, 1),
                           share_of_seoul_customers=round(c / tot_c, 4))
    return dict(segment='서울 주택용 계약전력 1~3kW', monthly=monthly,
                annual_kwh_per_customer=round(sum(v['kwh_per_customer'] for v in monthly.values()), 1) if len(monthly) == 12 else None)


WATER_XLSX = RAW_DIR / 'water_stats_2024.xlsx'
WATER_URL = 'https://mcee.go.kr/m/file/readDownloadFile.do?fileId=315840&fileSeq=5'   # 기후에너지환경부 2024년 상수도통계_공표.xlsx (정책자료 seq=8569, 2026-01-22 등록)


def summarize_water(xlsx=WATER_XLSX):
    """2024 상수도통계에서 서울 가정용 부과량·단가·급수인구·1인1일 가정용수사용량을 읽는다(지역 총량이며 세대 값이 아님). openpyxl 필요(이 갱신 스크립트에서만)."""
    try:
        import openpyxl
    except ImportError:
        sys.path.insert(0, str(ROOT / '_libs'))
        import openpyxl
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)

    def rows(sheet):
        return [list(r) for r in wb[sheet].iter_rows(values_only=True)]
    bill = rows('4-1-2 업종별 부과량분석')
    head = bill[5]
    c_pc = next(i for i, v in enumerate(head) if v and '1인1일가정' in str(v).replace(' ', ''))
    pick = lambda who: next(r for r in bill if str(r[0]) == '2024' and r[1] == who)
    se, lg = pick('서울특별시'), pick('(지자체)')
    pop = next(r for r in rows('2-2-1 급수인구현황') if str(r[0]) == '2024' and r[1] == '서울특별시' and r[2] == '계')
    f = lambda v: float(v)
    served = f(pop[4])
    return dict(source='기후에너지환경부 2024 상수도통계(2026-01-22 공개)', year=2024, scope='서울특별시 지방상수도 합계(지역 총량)',
                domestic_billed_m3=int(f(se[7])), domestic_billed_krw_thousand=int(f(se[6])), domestic_avg_won_per_m3=f(se[8]), domestic_first_m3_won=f(se[9]),
                served_population=int(served), l_per_capita_day_reported=f(se[c_pc]), l_per_capita_day_computed=round(f(se[7]) * 1000 / served / 365, 1),
                all_local_gov_l_per_capita_day_reported=f(lg[c_pc]),
                note='가정용 부과량 / 급수인구 / 365. 가구원수별·주택유형별 분포가 아니며 1인 가구의 집안 사용량이 아님.')


def build(offline=False):
    paths = {i: (RAW_DIR / f'raw_{i}.csv') if offline else download(i) for i in DATASETS}
    if not WATER_XLSX.exists() and not offline:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        WATER_XLSX.write_bytes(_get(WATER_URL))
    summary = dict(
        schema_version='recent-v1', built=str(date.today()),
        note='공공데이터 집계 요약. 고객(계량 단위) 평균이며 가구 단위 분포·소형 가구 값이 아님. 서비스 기본값을 대체하지 않는 참고·추세 정보.',
        gas=dict(source_id='15156658', **summarize_gas(_rows(paths['15156658']))),
        electricity=dict(source_id='15119479', **summarize_elec(_rows(paths['15119479']))),
        water=summarize_water() if WATER_XLSX.exists() else None)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    return summary


if __name__ == '__main__':
    s = build(offline='--offline' in sys.argv)
    print('gas 연간(서울 m3/수요가):', s['gas']['annual_m3_per_household'])
    print('전기 1~3kW 연 kWh/고객:', s['electricity']['annual_kwh_per_customer'], '| 월 수:', len(s['electricity']['monthly']))
