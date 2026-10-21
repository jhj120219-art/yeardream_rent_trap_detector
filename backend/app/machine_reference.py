"""Persistable analyst reference results; run analyst imports in a separate process."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from .maintenance_selection import grouped_references

HOUSING = {'APARTMENT': '아파트', 'MULTI_UNIT': '다세대·연립',
           'DETACHED_MULTI': '단독·다가구', 'OFFICETEL': '오피스텔'}
SOURCE = '분석가 utility 참고값: 에너지패널·수도요금·인터넷 참고범위 등 항목별 조건은 저장 result 확인, 개별 청구액 예측 아님'


class ReferenceScenario(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    target_month: StrictInt = Field(ge=1, le=12)
    household_size: StrictInt | None = Field(default=None, ge=1, le=6)
    heating_type: Literal['개별 도시가스', '지역난방', '중앙난방', '전기', '모름'] = '모름'
    gas_user: Literal['예', '아니오', '모름'] = '모름'
    metering: Literal['INDIVIDUAL', 'SHARED', 'UNKNOWN'] = 'UNKNOWN'
    acknowledge_reference_limits: StrictBool = False


class ReferenceUnavailable(RuntimeError):
    pass


def run_worker(payload, root):
    root = Path(root).resolve()
    if not (root / 'analysis_internal/utility/integration.py').is_file():
        raise ReferenceUnavailable('Analyst module not installed at configured path')
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    try:
        process = subprocess.run(
            [sys.executable, '-m', 'backend.app.machine_reference', '--worker', str(root)],
            input=json.dumps(payload, ensure_ascii=True, allow_nan=False),
            capture_output=True, encoding='utf-8', timeout=30, creationflags=flags,
            cwd=Path(__file__).resolve().parents[2])
        if process.returncode:
            raise ReferenceUnavailable('Analyst process unavailable')
        result = json.loads(process.stdout)
        if not isinstance(result, dict) or result.get('schema_version') != 'maintenance.v1':
            raise ReferenceUnavailable('Unsupported analyst result')
        if result.get('errors'):
            raise ReferenceUnavailable('Analyst reported an environment or contract error')
        return result
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ReferenceUnavailable('Analyst execution failed') from exc


def calculate(listing, scenario, root):
    raw = listing['input']; loc = raw['listing']; options = raw.get('options', {})
    payload = {'contract_version': 'FIVE_ITEMS_V1', 'request_id': listing['id'],
               'backend_options': options,
               'user': {'confirmed': True, 'metering': scenario.metering},
               'conditions': {'target_month': scenario.target_month,
                              'household_size': scenario.household_size,
                              'housing_type': HOUSING.get(loc.get('building_type')),
                              'area_m2': loc.get('area_m2') if loc.get('area_basis') == 'EXCLUSIVE' else None,
                              'heating_type': scenario.heating_type, 'gas_user': scenario.gas_user}}
    result = run_worker(payload, root)
    references = {}
    for row in result.get('utility_estimates', []):
        if row.get('utility_type') in ('WATER', 'ELECTRICITY', 'GAS', 'INTERNET') and row.get('estimate_status') == 'AVAILABLE':
            references[row['utility_type']] = {'low_krw': row.get('reference_low_krw'),
                                              'high_krw': row.get('reference_high_krw'), 'source': SOURCE}
    return {'listing_id': listing['id'], 'scenario': scenario.model_dump(), 'result': result,
            'groups': grouped_references(options, True, references),
            'provenance': {'geographic_scope': 'SEOUL_CITY', 'statistics_year': 2023,
                           'calculation_version': result.get('calculation_version'),
                           'tariff_version': result.get('tariff_version'), 'money_unit': 'KRW',
                           'notice': '서울 유사 가구의 참고값입니다. 실제 3건 비교·방식 선택은 미검증이며 정상 관리비나 실제 고지서 예측이 아닙니다.'}}


def worker_main(root):
    # The analyst module changes sys.path. Keep that change out of the API process.
    sys.path[:0] = [str(root.parent), str(root), str(root / 'analysis_internal')]
    payload = json.load(sys.stdin)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            from machine.analysis_internal.utility.integration import run_maintenance
            result = run_maintenance(payload)
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 0
    except Exception:
        # No server paths, private configuration, input or traceback in HTTP errors/logs.
        return 1


if __name__ == '__main__':
    raise SystemExit(worker_main(Path(sys.argv[2])) if len(sys.argv) == 3 and sys.argv[1] == '--worker' else 1)
