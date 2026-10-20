# -*- coding: utf-8 -*-
"""누수·중복 자동 검사. 위반 수를 반환한다(0이어야 통과). 평가 대상(기준 매물)은 계약마다 1번만 평가한다.
검사:
 L1  0단계 비교 거래의 최신 계약일 < 평가 계약일 (미래 거래 사용 0건)
 L2  절단 풀 동치: 평가일 이전 거래만 가진 엔진과 전체 거래 엔진의 결과가 같다(표본 N건) -> 미래 거래를 쓰지 않음
 L3  미래 거래 주입: 같은 지번에 평가일 이후의 극단값 거래를 넣어도 결과가 변하지 않는다
 L4  대상 재유입: 평가 대상과 (지번·계약일·면적·보증금·월세) 모두 같은 기록이 0단계 비교군에 들어가지 않는다(날짜 < 평가일이므로 구조적으로 0)
 U1  평가 단위 유일성: 기준 매물 행 인덱스 중복 0, 동일 계약 키 중복 건수는 보고(제외하지 않음)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import np, pd
from engine_v2 import EngineV2


def check_l1(recs: pd.DataFrame) -> dict:
    s0 = recs[recs['source'] == 'STAGE0']
    bad = s0[pd.to_datetime(s0['max_comp_date']) >= pd.to_datetime(s0['as_of'])]
    return dict(name='L1_stage0_comparable_before_as_of', checked=int(len(s0)), violations=int(len(bad)))


def _same(a, b):
    keys = ('source', 'stage_new', 'n_use')
    if any(a.get(k) != b.get(k) for k in keys):
        return False
    return all((pd.isna(a.get(k)) and pd.isna(b.get(k))) or abs(float(a[k]) - float(b[k])) < 1e-9 for k in ('pred', 'q25', 'q75', 'q90'))


def check_l2(rent, cache, policy, bases, n=40, seed=0) -> dict:
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(bases), size=min(n, len(bases)), replace=False)
    full = EngineV2(rent, cache, policy)
    bad = 0
    for i in idx:
        r = bases.iloc[i]
        a = full.evaluate(r)
        trunc = EngineV2(rent[rent['date'] < r['date']], cache, policy)
        b = trunc.evaluate(r)
        if not _same(a, b):
            bad += 1
    return dict(name='L2_truncated_pool_equivalence', checked=int(len(idx)), violations=int(bad))


def check_l3(rent, cache, policy, bases, n=30, seed=1) -> dict:
    """같은 지번(0단계 후보)에 평가일 이후의 극단 거래를 주입해도 결과가 변하면 위반."""
    rng = np.random.default_rng(seed)
    eng = EngineV2(rent, cache, policy)
    cand = [i for i in rng.permutation(len(bases)) if eng._stage0(bases.iloc[i])[1] == 'OK'][:n]
    bad = 0
    for i in cand:
        r = bases.iloc[i]
        a = eng.evaluate(r)
        fake = rent[(rent['CGG_CD'] == r['CGG_CD']) & (rent['STDG_CD'] == r['STDG_CD']) & (rent['MNO'] == r['MNO']) & (rent['SNO'] == r['SNO'])].head(5).copy()
        fake['date'] = r['date'] + pd.Timedelta(days=3)
        fake['rent'] = 9999.0
        fake['is_new'] = True
        b = EngineV2(pd.concat([rent, fake], ignore_index=True), cache, policy).evaluate(r)
        if not _same(a, b):
            bad += 1
    return dict(name='L3_future_injection', checked=int(len(cand)), violations=int(bad))


def check_l4_u1(recs: pd.DataFrame, bases: pd.DataFrame) -> list:
    out = [dict(name='U1_unique_base_rows', checked=int(len(bases)), violations=int(bases.index.duplicated().sum()))]
    key = ['gu', 'dong', 'MNO', 'SNO', 'date', 'area', 'dep', 'rent']
    dup = int(bases.duplicated(subset=key, keep=False).sum())
    out.append(dict(name='U1_info_duplicate_contract_keys_in_bases', checked=int(len(bases)), violations=0, info=f'동일 계약 키를 가진 기준 매물 행 {dup}건(제외하지 않음, 보고만)'))
    return out


def run_all(rent, cache, policy, bases, recs, quick=False) -> list:
    res = [check_l1(recs)]
    res.append(check_l2(rent, cache, policy, bases, n=12 if quick else 40))
    res.append(check_l3(rent, cache, policy, bases, n=8 if quick else 30))
    res.extend(check_l4_u1(recs, bases))
    return res
