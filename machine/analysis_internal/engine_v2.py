# -*- coding: utf-8 -*-
"""engine_v2 — 내부 후보 엔진. 0단계(같은 건물) + 기존 1~3차 + 새 신뢰도 + 마진 라벨.
analyze.py / 계약 v1.1 을 import 하지 않는다. 기존 compare_rent.compare 는 읽기 전용으로 호출(수정 없음).
입력은 내부 실험용 행(dict-like), 출력은 평가용 레코드(dict)."""
import json
from pathlib import Path

try:
    from common import ROOT, INTERNAL, np, pd
except ImportError:  # 패키지 형태로 불러올 때
    from .common import ROOT, INTERNAL, np, pd
import compare_rent as cr


class EngineV2:
    def __init__(self, rent: pd.DataFrame, building_cache: dict, policy: dict):
        self.policy = policy
        self.cache = building_cache
        self.rent = rent
        self.pool = cr.Pool(rent)
        new = rent[rent['is_new']]
        s0 = policy['stage0']
        ok = new['MNO'].notna() & new['SNO'].notna() & new['usage'].isin(s0['usages'])
        key = new['CGG_CD'] + '|' + new['STDG_CD'] + '|' + new['MNO'].fillna('') + '|' + new['SNO'].fillna('')
        self.lots = {k: g.sort_values('date') for k, g in new[ok].groupby(key[ok])}
        self.coef = None
        cf = INTERNAL / policy['trust']['coef_file']
        if cf.exists():
            self.coef = json.loads(cf.read_text(encoding='utf-8'))

    # ---------------------------------------------------------------- 0단계
    def _stage0(self, r):
        s0 = self.policy['stage0']
        if not s0['enabled'] or r['usage'] not in s0['usages'] or pd.isna(r['MNO']) or pd.isna(r['SNO']):
            return None, 'NO_LOT'
        key = f"{r['CGG_CD']}|{r['STDG_CD']}|{r['MNO']}|{r['SNO']}"
        g0 = self.lots.get(key)
        if g0 is None:
            return None, 'NO_POOL'
        nmain = self.cache.get((r['CGG_CD'], r['STDG_CD'], r['MNO'], r['SNO']))
        if s0['require_single_building'] and nmain != 1:
            return None, 'BUILDING_UNVERIFIED' if nmain is None else 'MULTI_BUILDING'
        dep = r['dep']
        band = dep * s0['dep_tol'] if dep >= 1000 else s0['dep_floor']
        m = ((g0['date'] < r['date']) & (g0['date'] >= r['date'] - pd.Timedelta(days=s0['window_days']))
             & ((g0['area'] - r['area']).abs() <= r['area'] * s0['area_tol']) & (g0['basement'] == r['basement'])
             & ((g0['dep'] - dep).abs() <= band))
        g = g0[m].drop_duplicates(subset=s0['dedupe_keys'])
        if len(g) < s0['min_n']:
            return None, 'N_TOO_SMALL'
        v = g['rent'].values.astype(float)
        return dict(vals=v, n=len(v), max_date=g['date'].max(), nmain=nmain, arch_nuniq=int(g['arch'].dropna().nunique())), 'OK'

    # ---------------------------------------------------------------- 평가
    def evaluate(self, r, as_of=None) -> dict:
        """r: 행(Series/dict) - gu, dong, usage, area, dep, rent, arch, basement, date, CGG_CD, STDG_CD, MNO, SNO."""
        as_of = pd.Timestamp(as_of or r['date'])
        rr = dict(r)
        rr['date'] = as_of
        L = dict(gu=r['gu'], dong=r['dong'], usage=r['usage'], area=float(r['area']), deposit=float(r['dep']), rent=float(r['rent']),
                 arch_year=None if pd.isna(r['arch']) else float(r['arch']), basement=bool(r['basement']))
        res = cr.compare(L, self.pool, as_of=as_of)
        rec = dict(usage=r['usage'], gu=r['gu'], rent=float(r['rent']), as_of=as_of)
        if res['status'] == 'ok':
            rec.update(rule_stage=int(res['stage'][0]), rule_pred=res['median'], rule_n=res['n'])
        else:
            rec.update(rule_stage=None, rule_pred=np.nan, rule_n=res.get('n'))
        s0, why = self._stage0(rr)
        rec['stage0_reason'] = why
        if s0 is not None:
            v = s0['vals']
            q = np.percentile(v, [10, 25, 50, 75, 90])
            rec.update(source='STAGE0', stage_new=0, n_use=s0['n'], pred=float(q[2]), q10=float(q[0]), q25=float(q[1]), q75=float(q[3]),
                       q90=float(q[4]), max_comp_date=s0['max_date'], nmain=s0['nmain'], arch_nuniq=s0['arch_nuniq'],
                       vals0=';'.join(f'{x:g}' for x in v))
        elif res['status'] == 'ok':
            rec.update(source='RULE', stage_new=rec['rule_stage'], n_use=res['n'], pred=res['median'], q10=res['q10'], q25=res['q25'],
                       q75=res['q75'], q90=res['q90'], max_comp_date=pd.NaT, nmain=np.nan, vals0='')
        else:
            rec.update(source='NONE', stage_new=np.nan, n_use=0, pred=np.nan, q10=np.nan, q25=np.nan, q75=np.nan, q90=np.nan,
                       max_comp_date=pd.NaT, nmain=np.nan, vals0='')
        if rec['source'] != 'NONE':
            rec['iqr'] = (rec['q75'] - rec['q25']) / rec['pred']
            rec['iqr90'] = (rec['q90'] - rec['q10']) / rec['pred']
            rec['logn'] = float(np.log(rec['n_use']))
            rec['err'] = abs(rec['pred'] - rec['rent']) / rec['rent'] if rec['rent'] > 0 else np.nan
            rec['rule_err'] = abs(rec['rule_pred'] - rec['rent']) / rec['rent'] if (pd.notna(rec['rule_pred']) and rec['rent'] > 0) else np.nan
        return rec

    # ---------------------------------------------------------------- 신뢰도
    def trust_prob(self, rec) -> float:
        """고정 계수 로지스틱(표준화). coef 파일이 없으면 NaN."""
        if self.coef is None or rec['source'] == 'NONE':
            return float('nan')
        z = self.coef['intercept']
        for f, w, mu, sd in zip(self.coef['features'], self.coef['coef'], self.coef['mean'], self.coef['scale']):
            z += w * (rec[f] - mu) / sd
        return float(1 / (1 + np.exp(-z)))

    def grade(self, p) -> str:
        t = self.policy['trust']
        return '높음' if p >= t['cut_high'] else ('보통' if p >= t['cut_mid'] else '낮음')

    # ---------------------------------------------------------------- 가격 라벨 (마진)
    def label(self, rent, rec, grade, margin=None):
        """반환 (label, reason). 라벨 의미는 기존과 같음: LOWER_RANGE(<Q25) / TYPICAL_RANGE / UPPER_RANGE(Q75~Q90) / UPPER_TAIL(>Q90).
        마진: 월세를 margin 만큼 낮춰(올려)도 같은 쪽 경계를 넘을 때만 강한 판정. 경계 근처는 UNRATED/BORDER."""
        P = self.policy['label']
        m = P['margin'] if margin is None else margin
        if rec['source'] == 'NONE':
            return 'UNRATED', 'NO_COMPARABLES'
        if grade in P['hold_when_grade']:
            return 'UNRATED', 'LOW_TRUST'
        if rec['stage_new'] in P['hold_stage']:
            return 'UNRATED', 'STAGE3_REFERENCE'
        q25, q75, q90 = rec['q25'], rec['q75'], rec['q90']
        if rent > q90:
            if rec['usage'] in P['no_tail_usages']:
                return ('UPPER_RANGE', 'TAIL_FORBIDDEN_USAGE') if (1 - m) * rent > q75 else ('UNRATED', 'BORDER_MARGIN')
            if rec['source'] == 'STAGE0' and rec['n_use'] < P['strong_label_min_n_stage0']:
                return ('UPPER_RANGE', 'STAGE0_SMALL_N') if (1 - m) * rent > q75 else ('UNRATED', 'BORDER_MARGIN')
            return ('UPPER_TAIL', 'OK') if (1 - m) * rent > q90 else ('UNRATED', 'BORDER_MARGIN')
        if rent > q75:
            return ('UPPER_RANGE', 'OK') if (1 - m) * rent > q75 else ('UNRATED', 'BORDER_MARGIN')
        if rent < q25:
            return ('LOWER_RANGE', 'OK') if (1 + m) * rent < q25 else ('UNRATED', 'BORDER_MARGIN')
        return 'TYPICAL_RANGE', 'OK'
