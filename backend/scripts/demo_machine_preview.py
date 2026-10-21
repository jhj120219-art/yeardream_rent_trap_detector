"""백엔드 + 머신 연동 시연: 매물을 등록하고 머신의 관리비 참고 비용(전기·수도·가스·인터넷)을 받아 표로 보여 준다.
임시 DB(SQLite)로 앱을 메모리에서 띄우므로 MySQL·실거래 데이터가 없어도 된다. 가상 매물이며 실제 광고가 아니다.
필요: machine 의 energy_reference_2023.csv (환경변수 ENERGY_REFERENCE_CSV 또는 machine/data/utility_stats/). 없으면 안내를 출력한다.
사용:  python -m backend.scripts.demo_machine_preview [--out backend/examples/machine_preview_demo]   (저장소 루트에서)
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(ROOT / 'backend' / 'examples' / 'machine_preview_demo'))
    a = ap.parse_args()
    from backend.app.config import Settings
    from backend.app.main import create_app
    from fastapi.testclient import TestClient
    from machine.analysis_internal.utility.data_files import energy_reference_csv, HOW_TO_ENERGY
    if not energy_reference_csv().exists():
        print(f'필요한 파일이 없습니다: {energy_reference_csv()}\n{HOW_TO_ENERGY}')
        return 2

    listing = {'schema_version': '1.1',
               'listing': dict(district_code='11620', legal_dong_code='1162010100', building_type='MULTI_UNIT', area_m2=20.0, area_basis='EXCLUSIVE',
                               deposit_10k_krw=1000, rent_10k_krw=55, built_year=2012, floor=3, floor_type='GROUND', floor_source='USER_CONFIRMED',
                               as_of='2026-10-01', address_text='가상 주소(시연)', unit_ho='301'),
               'options': dict(maintenance_10k_krw=9, electricity_in_maintenance='INCLUDED', water_in_maintenance='INCLUDED', gas_in_maintenance='INCLUDED',
                               internet_status='INCLUDED', other_in_maintenance='INCLUDED', other_cost_label='청소·공용관리 포함, 상세 금액 미기재'),
               'confirmation': {'user_confirmed': True, 'input_source': 'ADDRESS_MANUAL', 'confirmed_fields': ['floor']}}
    base = dict(target_month=10, household_size=1, area_m2=20.0, heating_type='개별 도시가스', gas_user='예', metering='INDIVIDUAL', acknowledge_reference_limits=True)
    scenarios = [
        ('A. 가을(10월) · 1인 · 20㎡ · 개별 도시가스', base),
        ('B. 겨울(1월) 같은 조건', dict(base, target_month=1)),
        ('C. 여름(8월) 같은 조건', dict(base, target_month=8)),
        ('D. 10월 · 난방 방식 모름 (가스는 보류)', dict(base, heating_type='모름', gas_user='모름')),
        ('E. 10월 · 2인 가구', dict(base, household_size=2)),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(db_path=Path(tmp) / 'demo.sqlite3', clean_csv=Path(tmp) / 'none.csv')
        s.machine_preview_enabled = True
        with TestClient(create_app(s)) as c:
            c.headers['Authorization'] = 'Bearer ' + c.post('/sessions').json()['token']
            r = c.post('/listings', json=listing)
            lid = r.json()['id']
            print('매물 등록:', r.status_code, lid, '| 광고 관리비 9만원(전기·수도·가스·인터넷·기타 포함)\n')
            out, md = [], ['# 백엔드 + 머신 연동 시연 (가상 매물, 참고 추정값)', '',
                           '관악구 다세대 20㎡, 광고 관리비 9만원에 전기·수도·가스·인터넷·기타(청소·공용) 포함. `POST /listings/{id}/maintenance-reference`', '',
                           '| 시나리오 | 전기 | 수도 | 가스 | 인터넷 | 상태 |', '|---|---|---|---|---|---|']
            for title, sc in scenarios:
                res = c.post(f'/listings/{lid}/maintenance-reference', json=sc).json()
                out.append(dict(scenario=title, request=sc, response=res))
                rows = {u['utility_type']: u for u in (res['result'] or {}).get('utility_estimates', [])}

                def cell(k):
                    u = rows.get(k)
                    if not u:
                        return '-'
                    return f'{u["reference_low_krw"]:,}~{u["reference_high_krw"]:,}원' if u['reference_low_krw'] is not None else '보류'
                line = f'| {title} | {cell("ELECTRICITY")} | {cell("WATER")} | {cell("GAS")} | {cell("INTERNET")} | {(res["result"] or {}).get("status", res["state"])} |'
                md.append(line)
                print(title)
                for k, name in (('ELECTRICITY', '전기'), ('WATER', '수도'), ('GAS', '가스'), ('INTERNET', '인터넷')):
                    print(f'   {name:3s} {cell(k)}')
                if res['result']:
                    print('   기타(OTHER): 광고 금액', res['result']['items']['OTHER']['advertised_amount_krw'], '(총액에서 역산하지 않음) | 확인 질문:',
                          len(res['result']['confirmation_questions']), '개')
                print()
            md += ['', '- 표의 금액은 2023년 가구에너지패널 서울 결과를 2026-10 요금표로 환산한 **참고 추정값**이며, 실제 청구액이나 정상 관리비가 아닙니다. 서로 다른 집단 평균을 각각 환산한 값들의 최소~최대입니다.',
                   '- 기타(청소·공용)는 광고에 명시된 금액만 표시하고 총액에서 역산하지 않습니다.', '- 가스는 개별 도시가스·사용 여부를 확인해야 계산하고, 모르면 보류합니다.',
                   '- 이 응답은 저장하지 않는 미리보기입니다(`MACHINE_MAINTENANCE_PREVIEW=true`).']
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.with_suffix('.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    outp.with_suffix('.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    print('저장:', outp.with_suffix('.md'), ',', outp.with_suffix('.json'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
