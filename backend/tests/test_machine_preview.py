"""머신 관리비 참고 비용 미리보기 엔드포인트 시험. energy_reference_2023.csv 가 없으면(ENERGY_REFERENCE_CSV 또는 machine/data/utility_stats/) 계산 시험은 건너뛴다."""
import os
import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app
from backend.tests.test_backend import payload, raw_rows
from backend.scripts.import_data import import_raw


def _energy_csv_available():
    try:
        from machine.analysis_internal.utility.data_files import energy_reference_csv
        return energy_reference_csv().exists()
    except Exception:
        return False


@pytest.fixture
def client(tmp_path, monkeypatch):
    def build(enabled):
        src = tmp_path / 'raw.csv'
        raw_rows().to_csv(src, index=False)
        clean = tmp_path / 'clean.csv'
        import_raw(src, clean)
        s = Settings(db_path=tmp_path / ('db_on.sqlite3' if enabled else 'db_off.sqlite3'), clean_csv=clean)
        s.machine_preview_enabled = enabled
        c = TestClient(create_app(s))
        c.__enter__()
        c.headers['Authorization'] = 'Bearer ' + c.post('/sessions').json()['token']
        return c
    made = []

    def factory(enabled):
        c = build(enabled)
        made.append(c)
        return c
    yield factory
    for c in made:
        c.__exit__(None, None, None)


def listing(c, **opts):
    body = payload(building_type='MULTI_UNIT')
    body['options'].update(dict(maintenance_10k_krw=9, electricity_in_maintenance='INCLUDED', water_in_maintenance='INCLUDED', gas_in_maintenance='INCLUDED',
                                internet_status='INCLUDED', other_in_maintenance='INCLUDED', other_cost_label='청소·공용'))
    body['options'].update(opts)
    r = c.post('/listings', json=body)
    assert r.status_code == 201, r.text
    return r.json()['id']


SCEN = dict(target_month=10, household_size=1, area_m2=20.0, heating_type='개별 도시가스', gas_user='예', metering='INDIVIDUAL', acknowledge_reference_limits=True)


def test_closed_by_default_and_capability_flag(client):
    c = client(False)
    lid = listing(c)
    assert c.post(f'/listings/{lid}/maintenance-reference', json=SCEN).status_code == 404
    assert c.get('/capabilities').json()['machine_maintenance_preview'] is False
    assert client(True).get('/capabilities').json()['machine_maintenance_preview'] is True


def test_requires_acknowledgement_and_valid_scenario(client):
    c = client(True)
    lid = listing(c)
    r = c.post(f'/listings/{lid}/maintenance-reference', json=dict(SCEN, acknowledge_reference_limits=False))
    assert r.status_code == 200 and r.json()['state'] == 'NEEDS_REVIEW' and r.json()['result'] is None
    assert c.post(f'/listings/{lid}/maintenance-reference', json=dict(SCEN, target_month=13)).status_code == 422
    assert c.post(f'/listings/{lid}/maintenance-reference', json=dict(SCEN, surprise=1)).status_code == 422
    assert c.post('/listings/nope/maintenance-reference', json=SCEN).status_code == 404


@pytest.mark.skipif(not _energy_csv_available(), reason='energy_reference_2023.csv 가 없음 (machine/check_data.py 안내 참고)')
def test_four_utilities_reference_and_no_other_generation(client):
    c = client(True)
    lid = listing(c)
    r = c.post(f'/listings/{lid}/maintenance-reference', json=SCEN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['state'] == 'CALCULATED'
    res = body['result']
    rows = {u['utility_type']: u for u in res['utility_estimates']}
    assert set(rows) == {'WATER', 'ELECTRICITY', 'GAS', 'INTERNET'}
    assert all(rows[k]['estimate_status'] == 'AVAILABLE' and rows[k]['reference_low_krw'] > 0 for k in rows)
    assert res['status'] == 'REFERENCE_ONLY'
    assert res['items']['OTHER']['advertised_amount_krw'] is None            # 기타를 총액에서 역산하지 않음
    assert res['decomposition']['enabled'] is False
    assert res['source_contract_version'] == 'FIVE_ITEMS_V1'
    text = r.text.replace('부당 청구액으로 해석하지 않음', '')          # never 목록의 부정 문구는 제외
    assert '부당' not in text and '과다 청구' not in text and '눈탱이' not in text
    # 같은 조건에서 겨울에는 가스가 여름보다 커진다 (참고값의 계절 변화)
    w = c.post(f'/listings/{lid}/maintenance-reference', json=dict(SCEN, target_month=1)).json()['result']
    s = c.post(f'/listings/{lid}/maintenance-reference', json=dict(SCEN, target_month=8)).json()['result']
    gas = lambda x: next(u for u in x['utility_estimates'] if u['utility_type'] == 'GAS')['reference_high_krw']
    assert gas(w) > gas(s)


@pytest.mark.skipif(not _energy_csv_available(), reason='energy_reference_2023.csv 가 없음')
def test_separate_charge_is_not_inside_maintenance_and_unknown_gas_is_held(client):
    c = client(True)
    lid = listing(c, electricity_in_maintenance='SEPARATE_CHARGE', gas_in_maintenance='INCLUDED')
    res = c.post(f'/listings/{lid}/maintenance-reference', json=dict(SCEN, heating_type='모름', gas_user='모름')).json()['result']
    assert [s['utility_type'] for s in res['separate_items']] == ['ELECTRICITY']
    gas = next(u for u in res['utility_estimates'] if u['utility_type'] == 'GAS')
    assert gas['estimate_status'] == 'HOLD' and gas['reference_low_krw'] is None


def test_missing_energy_file_is_reported_not_crashed(client, tmp_path, monkeypatch):
    from machine.analysis_internal.utility import data_files as D, reference as Rf
    monkeypatch.delenv(D.ENV_ENERGY, raising=False)
    monkeypatch.setattr(D, 'MACHINE', tmp_path / 'none')
    monkeypatch.setattr(D, 'HERE', tmp_path / 'none')
    monkeypatch.setattr(Rf, '_cache', None)
    c = client(True)
    lid = listing(c)
    r = c.post(f'/listings/{lid}/maintenance-reference', json=SCEN)
    assert r.status_code == 200 and r.json()['state'] == 'ERROR'
    assert r.json()['result']['errors'][0]['code'] == 'MISSING_DATA_FILE'


def _checkbox_listing(c):
    body = payload(building_type='MULTI_UNIT')
    body['options'].update(dict(maintenance_input_mode='CHECKBOX_TOTAL_V1', maintenance_10k_krw=9, electricity_in_maintenance='INCLUDED',
                                water_in_maintenance='INCLUDED', gas_in_maintenance='UNKNOWN', internet_status='INCLUDED', other_in_maintenance='INCLUDED'))
    r = c.post('/listings', json=body)
    assert r.status_code == 201, r.text
    return r.json()['id']


def test_report_reference_groups_stay_unconnected_when_flag_off(client):
    c = client(False)
    g = c.get(f'/listings/{_checkbox_listing(c)}/report').json()['maintenance_reference_groups']
    assert g['state'] == 'REFERENCE_NOT_CONNECTED'


@pytest.mark.skipif(not _energy_csv_available(), reason='energy_reference_2023.csv 가 없음')
def test_report_reference_groups_get_machine_amounts_without_inventing_unknown_items(client):
    c = client(True)
    g = c.get(f'/listings/{_checkbox_listing(c)}/report').json()['maintenance_reference_groups']
    rows = {r['item']: r for k in ('selected', 'unselected') for r in g[k]['items']}
    assert rows['ELECTRICITY']['reference_state'] == 'AVAILABLE' and rows['ELECTRICITY']['reference_low_krw'] > 0
    assert rows['INTERNET']['reference_state'] == 'AVAILABLE'
    assert rows['WATER']['reference_state'] == 'NO_REFERENCE' and rows['WATER']['reference_low_krw'] is None   # 가구원 수를 몰라 계산하지 않음
    assert rows['GAS']['reference_state'] == 'NO_REFERENCE'
    assert rows['OTHER']['reference_state'] == 'NO_REFERENCE'                                                 # 기타는 만들지 않음
    assert g['state'] == 'PARTIAL_REFERENCE' and g['selected']['reference_low_total_krw'] is None


def test_report_survives_missing_energy_file(client, tmp_path, monkeypatch):
    from machine.analysis_internal.utility import data_files as D, reference as Rf
    monkeypatch.delenv(D.ENV_ENERGY, raising=False)
    monkeypatch.setattr(D, 'MACHINE', tmp_path / 'none')
    monkeypatch.setattr(D, 'HERE', tmp_path / 'none')
    monkeypatch.setattr(Rf, '_cache', None)
    c = client(True)
    r = c.get(f'/listings/{_checkbox_listing(c)}/report')
    assert r.status_code == 200 and r.json()['maintenance_reference_groups']['state'] == 'REFERENCE_NOT_CONNECTED'
