"""머신(분석 파트) 관리비 참고 비용 연결 — 시연용 미리보기.
저장된 매물의 광고 관리비 입력(options, FIVE_ITEMS_V1)을 머신의 run_maintenance()에 그대로 넘기고, 사용자가 고른 시나리오(기준 월·가구원 수·난방 등)를 더해
전기·수도·가스·인터넷의 서울 비슷한 가구 기준 '참고 비용'을 돌려준다. 결과를 DB에 저장하지 않는다(상태 없음).
판정하지 않는다: 참고 추정값이며 실제 청구액이나 정상 관리비가 아니다. 기타 금액은 총액에서 역산하지 않는다.
환경변수 MACHINE_MAINTENANCE_PREVIEW=true 일 때만 열린다(기본 닫힘). 필요한 데이터 파일 ENERGY_REFERENCE_CSV 는 머신의 check_data.py 로 점검한다.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

HOUSING = {'APARTMENT': '아파트', 'MULTI_UNIT': '다세대·연립', 'DETACHED_MULTI': '단독·다가구', 'OFFICETEL': '오피스텔'}


class MachineScenario(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    target_month: StrictInt = Field(ge=1, le=12)
    household_size: StrictInt | None = Field(default=None, ge=1, le=6)
    area_m2: float | None = Field(default=None, gt=0, le=300, strict=True)        # 비우면 매물의 전용면적(area_basis=EXCLUSIVE)을 사용
    heating_type: Literal['개별 도시가스', '지역난방', '중앙난방', '전기', '모름'] = '모름'
    gas_user: Literal['예', '아니오', '모름'] = '모름'
    metering: Literal['INDIVIDUAL', 'SHARED', 'UNKNOWN'] = 'UNKNOWN'              # 전기·수도·가스를 세대별로 계량·정산하는지(사용자 확인)
    acknowledge_reference_limits: StrictBool = False


class MachineUnavailable(RuntimeError):
    """머신 코드나 필요한 데이터 파일을 불러오지 못함(서버 환경 문제)."""


def _run(payload):
    try:
        from machine.analysis_internal.utility.integration import run_maintenance
    except Exception as e:                                  # 이미지에 머신 관리비 코드가 없을 때 등
        raise MachineUnavailable('머신 관리비 모듈을 불러오지 못했습니다: ' + type(e).__name__) from e
    return run_maintenance(payload)


def preview(listing, scenario, listing_id=None):
    raw = listing['input']
    loc, opts = raw['listing'], raw.get('options', {})
    confirmed = bool(raw['confirmation']['user_confirmed']) and bool(listing['validation']['ok'])
    if not confirmed or not scenario.acknowledge_reference_limits:
        return {'version': 'machine-preview-1', 'state': 'NEEDS_REVIEW',
                'reasons': ['CONFIRMED_VALID_LISTING_AND_SCENARIO_ACKNOWLEDGEMENT_REQUIRED'], 'result': None,
                'notice': '확인을 마친 유효한 매물과 "참고값의 한계 확인"이 있어야 계산합니다.'}
    area = scenario.area_m2 if scenario.area_m2 is not None else (loc.get('area_m2') if loc.get('area_basis') == 'EXCLUSIVE' else None)
    conditions = dict(target_month=scenario.target_month, household_size=scenario.household_size, housing_type=HOUSING.get(loc.get('building_type')),
                      area_m2=area, heating_type=scenario.heating_type, gas_user=scenario.gas_user)
    payload = dict(contract_version='FIVE_ITEMS_V1', request_id=listing_id, backend_options=opts, conditions=conditions,
                   user=dict(confirmed=True, metering=scenario.metering))
    result = _run(payload)
    return {'version': 'machine-preview-1', 'state': 'ERROR' if result.get('errors') else 'CALCULATED', 'reasons': [], 'result': result,
            'notice': '서울 비슷한 가구의 참고 추정값입니다. 실제 청구액·평균 청구액·정상 관리비가 아니며 기타 금액은 총액에서 역산하지 않습니다.'}


SOURCE = '머신 참고값(서울 비슷한 가구 기준: 2023 가구에너지패널·2026 요금표, 개별 고지서 예측 아님)'


def report_references(listing, listing_id=None):
    """리포트의 항목별 참고금액(원)을 머신에서 받아온다. 사용자 시나리오가 없으므로 기준 월은 매물 기준일의 달이고
    가구원 수·난방은 알 수 없음으로 둔다 → 계산할 수 없는 항목(수도·가스)은 값을 만들지 않고 비운다.
    머신 오류·파일 누락이면 None(리포트는 기존대로 '자료 없음'). OTHER 는 만들지 않는다."""
    raw = listing['input']
    loc, opts = raw['listing'], raw.get('options', {})
    if not (raw['confirmation']['user_confirmed'] and listing['validation']['ok']):
        return None
    try:
        month = int(str(loc.get('as_of') or '')[5:7])
    except ValueError:
        return None
    if not 1 <= month <= 12:
        return None
    area = loc.get('area_m2') if loc.get('area_basis') == 'EXCLUSIVE' else None
    payload = dict(contract_version='FIVE_ITEMS_V1', request_id=listing_id, backend_options=opts, user=dict(confirmed=True, metering='UNKNOWN'),
                   conditions=dict(target_month=month, household_size=None, housing_type=HOUSING.get(loc.get('building_type')), area_m2=area,
                                   heating_type='모름', gas_user='모름'))
    try:
        result = _run(payload)
    except MachineUnavailable:
        return None
    if result.get('errors'):
        return None
    refs = {}
    for u in result.get('utility_estimates', []):
        if u.get('estimate_status') == 'AVAILABLE' and u.get('reference_low_krw') is not None:
            refs[u['utility_type']] = {'low_krw': u['reference_low_krw'], 'high_krw': u['reference_high_krw'], 'source': SOURCE}
    return refs or None
