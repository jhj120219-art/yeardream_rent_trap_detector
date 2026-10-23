# -*- coding: utf-8 -*-
"""최근 공공데이터 집계(recent_data/recent_seoul_summary.json)에서 '최근 참고' 정보를 돌려준다.
원칙: 기본 추정(2023 가구에너지패널 기준)을 바꾸지 않는다. 최근 값은 (1) 일관성 점검 (2) 추세 정보로만 나란히 보여 준다.
- 전기: 서울 주택용 계약전력 1~3kW 고객당 월 사용량(2025). '가구 분포'가 아니라 계량 단위 평균이며 빈 집·공용 계량이 섞일 수 있다.
- 가스: 한국가스공사 서울 수요가당 월 소비량(~2024). 절대 수준은 패널과 달라 쓰지 않고 연도별 변화율·월별 모양만 쓴다.
- 수도·인터넷: 최근 가구 단위 집계를 확보하지 못함 -> 기존 근거 유지(None 으로 표시).
"""
import json
from pathlib import Path

from .calc import electricity_bill, gas_bill

HERE = Path(__file__).resolve().parent
SUMMARY = HERE / 'recent_data' / 'recent_seoul_summary.json'
REGISTRY = HERE / 'recent_data' / 'source_registry.json'
_cache = None


def _load():
    global _cache
    if _cache is None:
        _cache = json.loads(SUMMARY.read_text(encoding='utf-8')) if SUMMARY.exists() else {}
    return _cache


def available():
    return bool(_load())


def electricity_recent(month):
    """서울 1~3kW 주택용 고객당 월 사용량(2025)과 그 사용량을 현재 요금표(2026-10)로 환산한 요금."""
    data = _load().get('electricity', {})
    key = next((k for k in data.get('monthly', {}) if int(k[5:7]) == month), None)
    if not key:
        return None
    m = data['monthly'][key]
    bill = electricity_bill(m['kwh_per_customer'], month)['total']
    return dict(source_id=data['source_id'], reference_period=key, group=data['segment'], kwh_per_customer=m['kwh_per_customer'],
                reported_won_per_customer=m['won_per_customer'], bill_at_tariff_2026_10=bill, customers=m['customers'],
                adjustment_applied=False,
                caveats=['고객(계량 단위) 평균이며 가구 분포 아님', '판매수입은 부가세·기금 포함 여부 미확인이라 환산 요금과 직접 비교하지 않음',
                         '빈 집·공용 계량 포함 가능', '단위는 데이터 페이지에 표시 없음(값 크기로 kWh·원으로 해석)'])


def gas_recent(month):
    """서울 도시가스 수요가당 월 소비량(최신 연도)과 전년 대비 변화율."""
    data = _load().get('gas', {})
    mon = data.get('monthly_m3_per_household', {})
    years = sorted(data.get('annual_m3_per_household', {}))
    if len(years) < 2:
        return None
    last, prev = years[-1], years[-2]
    ann = data['annual_m3_per_household']
    v = next((x for k, x in mon.items() if k[:4] == last and int(k[5:7]) == month), None)
    if v is None:
        return None
    return dict(source_id=data['source_id'], reference_period=f'{last}-{month:02d}', group='서울 도시가스 수요가 평균',
                m3_per_household=v, bill_at_tariff_2026_10=gas_bill(v)['total'],
                yoy_annual_change=round(ann[last] / ann[prev] - 1, 4), annual_m3=dict(prev=ann[prev], last=ann[last]),
                adjustment_applied=False,
                caveats=['2023 가구에너지패널 서울 평균(연 651N㎥)과 절대 수준이 달라 수준 비교·대체에 쓰지 않음(변화율·월별 모양만 참고)',
                         '취사 위주·대형 가구가 섞인 평균이라 소형 가구 값이 아님', '열량 42.6MJ/N㎥(가스공사 서울도시가스 12개월 평균)로 환산'])


def water_recent():
    """서울 2024 가정용 수도 지역 총량(기후에너지환경부 상수도통계)과, 지금 쓰는 요금 단가·세대원수별 상수와의 일치 여부."""
    w = _load().get('water')
    if not w:
        return None
    from .tariffs import WATER
    first_m3 = WATER['waterworks_won_per_m3']          # tariffs.py 는 값만 담는다(출처·상태는 tariffs_2026-10.json)
    return dict(w, tariff_first_m3_won_in_use=first_m3,
                tariff_matches_first_m3=(first_m3 == w['domestic_first_m3_won']) if first_m3 is not None else None,
                adjustment_applied=False,
                caveats=['지역 총량(가정용 부과량 / 급수인구)이며 세대원수별 분포가 아님', '1인 가구의 집안 사용량으로 쓰지 않음'])


def water_consistency(household_shares, l_per_day_by_size=None):
    """세대원수별 1일 사용량 상수를 가구원수 분포(비율)로 가중해 1인당 값으로 환산하고 공식 1인1일 가정용수사용량과 비교한다.
    household_shares: {가구원수: 비율}. 분포는 호출한 쪽이 공개 자료로 넣는다(마이크로데이터 파생 분포를 이 저장소에 넣지 않기 위해)."""
    w = _load().get('water')
    if not w:
        return None
    from .tariffs import SEOUL_WATER_L_PER_DAY
    tbl = l_per_day_by_size or SEOUL_WATER_L_PER_DAY
    tot = sum(household_shares.values())
    sh = {k: v / tot for k, v in household_shares.items()}
    per_hh = sum(sh[k] * tbl.get(min(k, 6), tbl[max(tbl)]) for k in sh)
    persons = sum(sh[k] * k for k in sh)
    implied = per_hh / persons
    return dict(implied_l_per_capita_day=round(implied, 1), reported_l_per_capita_day=w['l_per_capita_day_reported'],
                difference_pct=round(100 * (implied / w['l_per_capita_day_reported'] - 1), 1))


def recent_snapshot(month):
    """한 달 기준 '최근 참고' 묶음. 인터넷은 최근 집계가 없어 기존 근거 유지를 명시한다."""
    return dict(month=month, electricity=electricity_recent(month), gas=gas_recent(month),
                water=water_recent(), internet=None,
                notes=['판정이 아니라 참고 정보입니다. 기본 추정값은 2023 조사 기준이며 최근 값으로 보정하지 않았습니다.',
                       '수도는 서울 지역 총량(2024)이라 가구 값을 바꾸지 않고, 인터넷은 최근 집계가 없어 기존 근거를 유지합니다.'])
