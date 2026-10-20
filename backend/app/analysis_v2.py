"""Adapter for the analyst's unchanged candidate engine; existing v1.1 envelope retained."""
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
import analyze
import compare_rent
from normalize_listing import normalize_listing, analyze_raw
from machine.analysis_internal.engine_v2 import EngineV2
from .analysis_service import json_safe, load_pool

INTERNAL=Path(__file__).resolve().parents[2]/'machine/analysis_internal'


def load_cache(path):
    if not path or not Path(path).is_file():
        return {},'MISSING'
    frame=pd.read_csv(path,dtype=str,keep_default_na=False)
    columns={'CGG_CD','STDG_CD','MNO','SNO','ok','n_main'}
    if not columns.issubset(frame.columns):raise ValueError('Invalid building cache columns')
    result={}
    for row in frame.to_dict('records'):
        if row['ok']!='True':continue
        if not all(re.fullmatch(r'[0-9]{5}',row[c]) for c in ('CGG_CD','STDG_CD')):
            raise ValueError('Invalid building cache code')
        if not all(re.fullmatch(r'[0-9]{1,4}',row[c]) for c in ('MNO','SNO')):
            raise ValueError('Invalid building cache lot')
        if not re.fullmatch(r'[0-9]+',row['n_main']):raise ValueError('Invalid building count')
        key=(row['CGG_CD'],row['STDG_CD'],row['MNO'].zfill(4),row['SNO'].zfill(4))
        count=int(row['n_main'])
        if key in result and result[key]!=count:raise ValueError('Conflicting building counts')
        result[key]=count
    return result,'READY' if result else 'EMPTY'


class V2Service:
    def __init__(self,csv_path,cache_path=None,same_building_enabled=False):
        self.legacy_pool=load_pool(csv_path) # Reuse strict CSV validation, including boolean strings.
        frame=pd.read_csv(csv_path,dtype=str)
        if not {'MNO','SNO','flr'}.issubset(frame.columns):raise ValueError('V2 requires lot and floor columns')
        for column in ('is_new','basement','dup_suspect'):frame[column]=frame[column].map({'True':True,'False':False})
        frame['date']=pd.to_datetime(frame['date'])
        for column in ('area','dep','rent','arch','flr'):frame[column]=pd.to_numeric(frame[column],errors='coerce')
        for column in ('MNO','SNO'):
            values=frame[column]
            if (values.notna() & ~values.str.fullmatch(r'[0-9]{1,4}',na=False)).any():
                raise ValueError('Invalid lot data; never infer missing lot numbers')
            frame[column]=values.str.zfill(4)
        self.frame=frame
        self.same_building_enabled=same_building_enabled
        self.cache,self.cache_status=load_cache(cache_path) if same_building_enabled else ({},'DISABLED')
        self.policy=json.loads((INTERNAL/'configs/candidate_v2.json').read_text(encoding='utf-8'))
        if not same_building_enabled:
            self.policy['stage0']['enabled']=False
        self.engines={}
        for usage,group in frame.groupby('usage'):
            # Analyst stage0 groups lots without usage in the key. Isolate input by usage
            # so apartments/officetels at the same parcel cannot contaminate each other.
            engine=EngineV2(group,self.cache,self.policy)
            if engine.coef is None:raise ValueError('Missing analyst confidence coefficients')
            self.engines[usage]=engine

    def run(self,raw):
        base=json_safe(analyze_raw(raw,self.legacy_pool))
        meta={'version':self.policy['version'],'adapter':'backend-v2.1',
              'comparison_mode':'SAME_BUILDING_THEN_NEIGHBORHOOD' if self.same_building_enabled else 'NEIGHBORHOOD',
              'same_building_enabled':self.same_building_enabled,'building_cache_status':self.cache_status,'same_building_requires_verified_single_main':True}
        if base['status'] in ('INPUT_REVIEW_REQUIRED','OUT_OF_SCOPE'):
            return dict(base,analysis_engine=meta)
        n=normalize_listing(raw);p=n['payload'];listing=raw['listing']
        gu=analyze.SUPPORTED_GU.get(p['district_code']);usage=analyze.BUILDING_TYPES[p['building_type']]
        locations=self.frame[self.frame['CGG_CD']==p['district_code']]
        legal=p.get('legal_dong_code')
        if legal:locations=locations[locations['STDG_CD']==legal[5:]]
        else:locations=locations[locations['dong']==p.get('dong')]
        pairs=locations[['STDG_CD','dong']].drop_duplicates()
        if pairs.empty or usage not in self.engines:
            result=analyze._base_result('INSUFFICIENT_DATA')
            return dict(result,analysis_engine=meta,options=n['options'])
        dong=pairs.iloc[0]['dong'];dong_code=pairs.iloc[0]['STDG_CD'] if len(pairs)==1 else None
        when=pd.Timestamp(p.get('as_of') or self.legacy_pool.max_date+pd.Timedelta(days=1))
        main=listing.get('main_no');sub=listing.get('sub_no')
        valid_lot=main is not None and dong_code is not None
        row=dict(gu=gu,dong=dong,usage=usage,area=p['area_m2'],dep=p['deposit_10k_krw'],
                 rent=p['rent_10k_krw'],arch=p.get('built_year',np.nan),
                 basement=p.get('floor_type')=='BASEMENT',date=when,CGG_CD=p['district_code'],
                 STDG_CD=dong_code or '',MNO=str(main).zfill(4) if valid_lot else np.nan,
                 SNO=str(sub or '0').zfill(4) if valid_lot else np.nan)
        engine=self.engines[usage];rec=engine.evaluate(row,as_of=when)
        meta.update(source=rec['source'],stage0_reason=rec['stage0_reason'] if self.same_building_enabled else 'DISABLED_BY_SCOPE')
        result=analyze._base_result('INSUFFICIENT_DATA',data_as_of=str(self.legacy_pool.max_date.date()))
        result.update(analysis_engine=meta,options=n['options'],input_notes=n['notes'])
        if rec['source']=='NONE':
            result['reason_codes']=['NO_COMPARABLES'];return json_safe(result)
        probability=engine.trust_prob(rec)
        grade=engine.grade(probability)
        label,reason=engine.label(row['rent'],rec,grade)
        # Preserve trusted input handling; demo's supply-area and detached-floor holds.
        if usage=='단독다가구':
            if p.get('floor_type')=='BASEMENT':label,reason='UNRATED','BASEMENT_LISTING'
            elif p.get('floor_type')!='GROUND':label,reason='UNRATED','FLOOR_UNCONFIRMED'
            elif grade!='높음':label,reason='UNRATED','LOW_TRUST'
            elif label in ('UPPER_RANGE','UPPER_TAIL') and row['rent']<=rec['q75']*1.10:
                label,reason='UNRATED','BORDER_MARGIN'
        if label=='UPPER_TAIL' and grade!='높음':
            label,reason='UPPER_RANGE','HIGH_GRADE_REQUIRED'
        if p['area_basis'] in ('SUPPLY','CONTRACT') and usage!='단독다가구':
            label,reason='UNRATED','AREA_BASIS_UNVERIFIED'
        ratio=row['rent']/rec['pred']
        suspicious=row['rent']<3 or row['rent']>500 or ratio>2.5 or ratio<0.4
        if suspicious:label,reason='UNRATED','INPUT_CHECK'
        status='INPUT_REVIEW_REQUIRED' if suspicious else ('COMPARED' if label!='UNRATED' else 'REFERENCE_ONLY')
        stage=int(rec['stage_new'])
        selected=self.policy['stage0'] if stage==0 else compare_rent.STAGES[stage-1]
        scope='SAME_LOT_VERIFIED_SINGLE_MAIN' if stage==0 else ('DISTRICT' if stage==3 else 'LEGAL_DONG')
        conditions={'area_tolerance':selected.get('area_tol',selected.get('area')),
                    'built_year_tolerance':selected.get('arch'),
                    'deposit_tolerance':selected.get('dep_tol',selected.get('dep')),
                    'scope':{'SAME_LOT_VERIFIED_SINGLE_MAIN':'같은 지번·주건축물 1동 확인','DISTRICT':'같은 자치구 전체','LEGAL_DONG':'같은 법정동'}[scope],
                    'scope_code':scope}
        prices={key:float(rec[column]) for key,column in [('q10','q10'),('q25','q25'),('median','pred'),('q75','q75'),('q90','q90')]}
        result.update(status=status,stage=stage,sample_count=int(rec['n_use']),price_label=label,
            confidence_grade=analyze.GRADE_EN[grade],prices_10k_krw=prices,
            rent_difference_10k_krw=row['rent']-rec['pred'],rent_difference_pct=ratio-1,
            reason_codes=[reason],hold_reasons=[reason] if label=='UNRATED' else [],
            reference={'source':analyze.DATA_SOURCE,'contract_type':'NEW','renewals_excluded':True,
                       'renewals_excluded_in_data_for_gu':getattr(self.legacy_pool,'renewals_excluded_by_gu',{}).get(gu),
                       'months_used':None if stage==0 else selected['months'],
                       'window_days':selected.get('window_days'),'search_stage':stage,
                       'conditions':conditions,'sample_count':int(rec['n_use']),
                       'relaxed_conditions':[] if stage==0 else [analyze.RELAX_CODES[k] for k in ('area','arch','dep','months','scope') if selected[k]!=compare_rent.STAGES[0][k]],'prices_10k_krw':prices,
                       'notice':'같은 동네의 유사 거래부터 비교하고 자료가 부족하면 조건과 지역 범위를 넓힙니다.' if not self.same_building_enabled else '같은 지번의 주건축물 1동 확인 시에만 같은 건물 비교를 적용합니다.'},
            confidence_details={'method':'ANALYST_V2_FIXED_LOGISTIC','grade':analyze.GRADE_EN[grade],
                                'comparability_score':None,'data_sufficiency_score':None,
                                'recent_share_6m':None,'relative_iqr':float(rec['iqr']),
                                'notice':'조건별 과거 평가 기반 등급이며 현재 가격 정확도나 사기 확률이 아닙니다.'},
            messages=[analyze.MESSAGES[label]],warnings=['V2_CANDIDATE_POLICY'],
            warning_texts={'V2_CANDIDATE_POLICY':'분석 담당 개선판을 연결한 결과입니다. 개별 비교 거래 목록은 아직 제공하지 않습니다.'},
            floor=base.get('floor'))
        if suspicious:
            result.update(errors=['RENT_REVIEW_REQUIRED'],input_issues=['RENT_REVIEW_REQUIRED'],messages=['월세 금액과 단위를 다시 확인해 주세요.'])
        for code in ('DATA_STALE','AREA_ASSUMED_EXCLUSIVE'):
            if code in base.get('warnings',[]):
                result['warnings'].append(code)
                result['warning_texts'][code]=analyze.WARNING_TEXT.get(code,code)
        if self.same_building_enabled and self.cache_status!='READY':
            result['warnings'].append('BUILDING_CACHE_UNAVAILABLE')
            result['warning_texts']['BUILDING_CACHE_UNAVAILABLE']='건물 동수 확인 자료가 없어 같은 건물 비교를 적용하지 않았습니다.'
        return json_safe(result)
