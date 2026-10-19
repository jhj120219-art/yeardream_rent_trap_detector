"""공개 통계·명시한 사용량에 따른 참고 견적. 월세 분석·적정 관리비 판정과 별개다."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from .report import money

KESIS='https://kesis.keei.re.kr/board.es?mid=a10202030100&bid=0009'
ELECTRICITY='https://www.data.go.kr/data/15104442/fileData.do'
FUEL='https://www.kepco.co.kr/home/media/newsroom/notice/boardView.do?boardMngNo=14&boardNo=2759'
GAS='https://www.seoulgas.co.kr/mobile/payment/gasPayTable'
WATER='https://i121.seoul.go.kr/cs/cyber/front/cgcalc/NR_cgCalcGeneralPurpose.do'
WATER_USE='https://arisu.seoul.go.kr/home/sub?dsn=1704067300-000-692&menukey=7205&mode=view'
INTERNET='https://product.kt.com/wDic/index.do?CateCode=6005&FilterCode=118'

# 공개 통계는 주택유형과 지역을 넘어 보간하지 않는다.
PROFILES={
    'APARTMENT':{'label':'서울 아파트','annual_kwh':3140.3,'annual_gas_mcal':6118.7,'cells':['G36','G53']},
    'MULTI_UNIT':{'label':'서울 다세대/연립/기타','annual_kwh':2855.8,'annual_gas_mcal':6524.8,'cells':['F36','F53']},
}


class UtilityScenario(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    scenario_month: Literal['2026-10','2026-11','2026-12']
    acknowledge_reference_limits: StrictBool=False
    use_public_reference: StrictBool=False
    electricity_kwh: float | None=Field(default=None,ge=0,le=1000,strict=True)
    electricity_contract: Literal['LOW_VOLTAGE','UNKNOWN']='UNKNOWN'
    gas_mj: float | None=Field(default=None,ge=0,le=100000,strict=True)
    gas_supplier: Literal['SEOUL_CITY_GAS_SEOUL','UNKNOWN']='UNKNOWN'
    household_size: StrictInt | None=Field(default=None,ge=1,le=6)
    water_m3: float | None=Field(default=None,ge=0,le=1000,strict=True)
    water_individual_meter: StrictBool=False
    water_meter_mm: Literal[15] | None=None
    internet_plan: Literal['KT_SLIM_100M_3Y'] | None=None


def catalog():
    return {'version':'public-reference-scenario-1','supported_months':['2026-10','2026-11','2026-12'],
            'profiles':PROFILES,'statistics_year':2023,'source':KESIS,
            'source_sheet':'가. 주택종류별','geographic_scope':'SEOUL_CITY',
            'tariff_status':'REFERENCE_ASSUMPTIONS_NOT_BILLING_CERTIFIED',
            'not_supported':['OFFICETEL_SEPARATE_STATISTICS','DISTRICT_OR_DONG_AVERAGE','AREA_SPECIFIC_VILLA_AVERAGE'],
            'notice':'과거 평균 사용량의 요금 환산 예시이며 평균 청구액이 아닙니다. 면적별·구/동별·현재 개별 사용량으로 추정하지 않습니다.'}


def electricity(kwh):
    base=910 if kwh<=200 else 1600 if kwh<=400 else 7300
    energy=min(kwh,200)*120+min(max(kwh-200,0),200)*214.6+max(kwh-400,0)*307.3
    climate=kwh*9
    fuel=kwh*5
    subtotal=base+energy+climate+fuel
    return round(subtotal*1.127),{'base_won':base,'energy_won':round(energy,2),
        'climate_won':round(climate,2),'fuel_won':round(fuel,2),
        'vat_won':round(subtotal*.1,2),'fund_won':round(subtotal*.027,2),
        'rates':{'climate_per_kwh':9,'fuel_per_kwh':5,'vat_pct':10,'fund_pct':2.7},
        'formula':'(기본 + 구간별 전력량 + kWh×9 + kWh×5) × (1+0.10+0.027)',
        'notice':'비하계 저압, 할인·검침 안분·원단위 절사 제외. 요금 가정을 적용한 참고값입니다.'}


def estimate(listing, scenario):
    raw=listing['input'];opts=raw.get('options',{});loc=raw['listing']
    confirmed=raw['confirmation']['user_confirmed']
    acknowledged=scenario.acknowledge_reference_limits
    seoul=str(loc.get('district_code','')).startswith('11')
    profile=PROFILES.get(loc.get('building_type')) if seoul else None
    mapping={'ELECTRICITY':'electricity_in_maintenance','GAS':'gas_in_maintenance',
             'WATER':'water_in_maintenance','INTERNET':'internet_status'}
    rows=[]
    for key,field in mapping.items():
        stated=opts.get(field)
        inclusion=stated if stated in ['INCLUDED','SEPARATE_CHARGE'] else 'UNKNOWN'
        row={'item':key,'inclusion':inclusion,'state':'INPUT_REQUIRED','reasons':[],
             'estimated_monthly_won':None,'additional_to_maintenance_won':None,
             'usage':None,'source':None,'calculation':None}
        rows.append(row)
        if not confirmed or not acknowledged or not listing['validation']['ok']:
            row.update(state='NEEDS_REVIEW',reasons=['CONFIRMED_VALID_LISTING_AND_SCENARIO_ACKNOWLEDGEMENT_REQUIRED'])
            continue
        if inclusion=='INCLUDED':
            row.update(state='INCLUDED_IN_MAINTENANCE',additional_to_maintenance_won=0,
                       reasons=['INCLUDED_NOT_FREE_USAGE'])
            continue
        if key in ['GAS','WATER'] and not seoul:
            row.update(state='UNSUPPORTED_REGION',reasons=['SEOUL_TARIFF_ONLY'])
            continue
        used_reference=False
        if key in ['ELECTRICITY','GAS']:
            quantity=scenario.electricity_kwh if key=='ELECTRICITY' else scenario.gas_mj
            if quantity is None and scenario.use_public_reference:
                if profile is None:
                    row.update(state='NO_MATCHED_REFERENCE',reasons=['NO_SUPPORTED_CITY_AND_HOUSING_PROFILE'])
                    continue
                used_reference=True
                quantity=profile['annual_kwh']/12 if key=='ELECTRICITY' else profile['annual_gas_mcal']*4.1868/12
                row['source']={'type':'PUBLIC_STATISTICS','url':KESIS,'year':2023,
                    'scope':profile['label'],'sheet':'가. 주택종류별',
                    'cell':profile['cells'][0 if key=='ELECTRICITY' else 1],
                    'aggregation':'ANNUAL_DIVIDED_BY_12','area_specific':False,
                    'notice':'다세대/연립/기타는 빌라만의 표본이 아닙니다. 계절별·개별 예측값이 아닙니다.'}
            elif quantity is not None:
                row['source']={'type':'USER_SCENARIO_USAGE','statistics_year':None}
            if quantity is None:
                row['reasons']=['USAGE_OR_PUBLIC_REFERENCE_REQUIRED'];continue
            row['usage']={'quantity':round(quantity,6),'unit':'kWh' if key=='ELECTRICITY' else 'MJ'}
            if key=='ELECTRICITY':
                if scenario.electricity_contract!='LOW_VOLTAGE':
                    row['reasons']=['LOW_VOLTAGE_CONTRACT_CONFIRMATION_REQUIRED'];continue
                amount,calc=electricity(quantity)
                calc.update(tariff_url=ELECTRICITY,tariff_table_date='2024-07-01',fuel_url=FUEL)
            else:
                if scenario.gas_supplier!='SEOUL_CITY_GAS_SEOUL':
                    row['reasons']=['GAS_SUPPLIER_CONFIRMATION_REQUIRED'];continue
                amount=round((quantity*22.5268+1250)*1.1)
                calc={'unit_won_per_mj':22.5268,'base_won':1250,'vat_pct':10,
                      'formula':'(MJ×22.5268 + 1250)×1.1','tariff_url':GAS,'tariff_date':'2026-10-01',
                      'notice':'할인·정산·교체비 제외. 입력열량 또는 통계열량 사용, 검침량을 임의로 MJ로 변환하지 않습니다.'}
        elif key=='WATER':
            quantity=scenario.water_m3
            if quantity is None and scenario.use_public_reference and scenario.household_size==1:
                quantity=7.92;used_reference=True
                row['source']={'type':'PUBLIC_STATISTICS','url':WATER_USE,'year':2021,
                    'scope':'서울 1인 세대','daily_litres':264,'days_assumed':30,'housing_specific':False}
            elif quantity is not None:
                row['source']={'type':'USER_SCENARIO_USAGE'}
            if quantity is None:
                row['reasons']=['WATER_USAGE_OR_ONE_PERSON_REFERENCE_REQUIRED'];continue
            row['usage']={'quantity':quantity,'unit':'m3'}
            variable=quantity*(580+480+170)
            calc={'variable_won':round(variable),'water_per_m3':580,'sewer_per_m3':480,
                  'fund_per_m3':170,'tariff_url':WATER,'sewer_tariff_year':2026,
                  'formula':'m3×(580+480+170) + 계량기 기본요금'}
            row['calculation']=calc
            if not scenario.water_individual_meter or scenario.water_meter_mm!=15:
                row.update(state='PARTIAL_ONLY',reasons=['INDIVIDUAL_15MM_METER_REQUIRED_NO_SHARED_ALLOCATION'])
                continue
            amount=round(variable+1080);calc['meter_base_won']=1080
        else:
            if scenario.internet_plan is None:
                row['reasons']=['INTERNET_PLAN_REQUIRED'];continue
            amount=22000
            row['source']={'type':'PUBLIC_PLAN','url':INTERNET,'plan':'KT_SLIM_100M_3Y'}
            calc={'monthly_won':22000,'formula':'공개 상품 월요금',
                  'notice':'3년 약정 표준요금 예시. 설치·공유기·결합/온라인 할인·건물단체계약 제외. 설치 가능 여부를 확인한 결과는 아닙니다.'}
        row.update(state='ESTIMATED',estimated_monthly_won=amount,calculation=calc)
        if inclusion=='SEPARATE_CHARGE':row['additional_to_maintenance_won']=amount
        else:row['reasons'].append('INCLUSION_UNKNOWN_NOT_ADDED')
        if used_reference:row['reasons'].append('HISTORICAL_AGGREGATE_NOT_INDIVIDUAL_PREDICTION')
    complete=all(r['additional_to_maintenance_won'] is not None for r in rows)
    subtotal=money(loc.get('rent_10k_krw'));fee=money(opts.get('maintenance_10k_krw'))
    quoted=round((subtotal+fee)*10000) if confirmed and acknowledged and listing['validation']['ok'] and subtotal is not None and fee is not None else None
    extra=sum(r['additional_to_maintenance_won'] for r in rows) if complete else None
    return {'version':'public-reference-scenario-1','scenario_month':scenario.scenario_month,
            'state':('NEEDS_REVIEW' if not confirmed or not acknowledged or not listing['validation']['ok'] else
                     'ESTIMATED' if complete and quoted is not None else 'PARTIAL'),
            'items':rows,'quoted_rent_and_maintenance_won':quoted,
            'additional_utilities_won':extra,
            'scenario_monthly_subtotal_won':quoted+extra if quoted is not None and extra is not None else None,
            'notice':'요금 가정을 적용한 참고 견적이며 실제 평균 청구액·동네 시세·평당 관리비가 아닙니다. 주차·일회성 비용 등은 제외됩니다.'}
