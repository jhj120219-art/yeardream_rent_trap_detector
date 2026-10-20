# -*- coding: utf-8 -*-
"""통합 평가 하네스. 기존 방식(1~3차)과 engine_v2 를 같은 기준 매물에서 비교하고, 매니페스트(해시·시드·정책·버전)를 남긴다.
설계 모드(기본):  python run_backtest.py            -> 신뢰도 계수를 구 단위 교차검증으로 평가하고 전체 학습 계수를 configs/trust_coef_v2.json 에 기록
고정 평가 모드:   python run_backtest.py --frozen --data PATH --label holdout_songpa_gangbuk
                  -> 저장된 계수·정책만 사용. 계수/정책 파일이 없거나 해시가 --expect-policy-hash 와 다르면 중단.
결과: results/<run_id>/{records.csv, report.json, manifest.json}
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import ROOT, INTERNAL, np, pd, sha256, code_version, load_policy, load_rent, load_building_cache, make_bases
from engine_v2 import EngineV2
import metrics as M
import leakage_checks as LC

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=str(ROOT / 'output' / 'clean_rent_data.csv'))
ap.add_argument('--policy', default=str(INTERNAL / 'configs' / 'candidate_v2.json'))
ap.add_argument('--frozen', action='store_true')
ap.add_argument('--label', default='design6')
ap.add_argument('--expect-policy-hash', default=None)
ap.add_argument('--quick-leakage', action='store_true')
ap.add_argument('--no-leakage', action='store_true')
ap.add_argument('--building-cache', default=None, help='정책의 건물 캐시 대신 사용할 CSV(홀드아웃용). 매니페스트에 해시 기록')
ap.add_argument('--all-rows', action='store_true', help='기준 매물 대신 해당 데이터의 신규 계약 전체를 평가(고정 평가 모드용)')
a = ap.parse_args()

policy = load_policy(a.policy)
pol_hash = sha256(a.policy)
if a.expect_policy_hash and a.expect_policy_hash != pol_hash:
    sys.exit(f'정책 해시 불일치: {pol_hash} != {a.expect_policy_hash}')
coef_path = INTERNAL / policy['trust']['coef_file']
if a.frozen and not coef_path.exists():
    sys.exit('고정 평가 모드에는 저장된 신뢰도 계수가 필요합니다')

rent = load_rent(a.data)
CACHE_PATH = Path(a.building_cache) if a.building_cache else ROOT / policy['stage0']['building_cache']
cache = load_building_cache(CACHE_PATH)
ev = policy['evaluation']
bases = make_bases(rent, ev['seed'], ev['bases_per_gu'], ev['recent_months']) if not a.all_rows else rent[rent['is_new']].reset_index(drop=True)
print(f'[{a.label}] 평가 대상 {len(bases)}건, 건물 캐시 {len(cache)}곳, 정책 {policy["version"]}', flush=True)

t0 = time.time()
eng = EngineV2(rent, cache, policy)
recs = []
for k, (_, r) in enumerate(bases.iterrows()):
    recs.append(eng.evaluate(r))
    if k and k % 2000 == 0:
        print(f'  {k}/{len(bases)} ({time.time()-t0:.0f}s)', flush=True)
R = pd.DataFrame(recs)
R['base_idx'] = np.arange(len(R))
valid = R['source'] != 'NONE'
print(f'평가 가능 {int(valid.sum())}건 / 0단계 적용 {int((R.source=="STAGE0").sum())}건 ({time.time()-t0:.0f}s)', flush=True)

# 설계 모드의 기준선 일치 확인(기존 백테스트와 같은 표본·같은 값인지)
base_check = None
bt_path = ROOT / 'output' / 'backtest_all.csv'
if not a.frozen and not a.all_rows and bt_path.exists():
    bt = pd.read_csv(bt_path)
    same_n = len(bt) == len(R)
    same_actual = bool(same_n and np.allclose(bt['actual'].values, R['rent'].values))
    same_rule = bool(same_n and np.allclose(bt['median'].fillna(-1).values, R['rule_pred'].fillna(-1).values, atol=0.051))
    base_check = dict(same_n=same_n, same_actual=same_actual, same_rule_pred=same_rule)
    assert same_actual and same_rule, f'기준선 불일치: {base_check}'

# ---------------------------------------------------------------- 신뢰도
V = R[valid].copy()
feats = policy['trust']['features']
report = dict(label=a.label, n_bases=int(len(R)), n_valid=int(valid.sum()), n_stage0=int((R.source == 'STAGE0').sum()))
if a.frozen:
    V['p20'] = [eng.trust_prob(rec) for rec in V.to_dict('records')]
    full_coef = None
else:
    loo, full_coef = M.fit_trust(V, feats)
    V['p20'] = loo
    report['trust_scores_loo'] = M.trust_scores(V, V['p20'])
    coef_path.write_text(json.dumps(full_coef, ensure_ascii=False, indent=1), encoding='utf-8')
if a.frozen:
    report['trust_scores'] = M.trust_scores(V, V['p20'].values)
V['grade'] = [eng.grade(p) for p in V['p20']]
report['grade_table'] = M.grade_table(V)
report['grade_monotonic'] = M.is_monotonic(report['grade_table'])
report['calibration'] = M.calibration_table(V, V['p20'].values)
# 기존 점수(참고): 같은 표본에서 기존 방식의 신뢰 지표는 하네스 밖(backtest_all.csv)에 있으므로 여기서는 비교 대상에서 제외

# ---------------------------------------------------------------- 정확도: 기존 vs v2 (같은 표본)
both = V[V['rule_err'].notna()]
report['accuracy'] = dict(
    n_common=int(len(both)),
    baseline_median_err_pct=round(M.med_pct(both['rule_err']), 2), v2_median_err_pct=round(M.med_pct(both['err']), 2),
    baseline_within20_pct=round(M.within(both['rule_err']), 1), v2_within20_pct=round(M.within(both['err']), 1),
    all_valid_v2_median_err_pct=round(M.med_pct(V['err']), 2), all_valid_v2_within20_pct=round(M.within(V['err']), 1),
    stage0_only=dict(n=int((both.source == 'STAGE0').sum()),
                     v2_median_err_pct=round(M.med_pct(both[both.source == 'STAGE0']['err']), 2),
                     baseline_median_err_pct=round(M.med_pct(both[both.source == 'STAGE0']['rule_err']), 2)),
    by_usage={u: dict(n=int(len(x)), baseline=round(M.med_pct(x['rule_err']), 2), v2=round(M.med_pct(x['err']), 2))
              for u, x in both.groupby('usage')})
# 건물 단위 부트스트랩 (0단계 적용 사례, 건물 = 지번 키)
s0 = both[both['source'] == 'STAGE0'].copy()
if len(s0):
    key = bases.loc[s0['base_idx'], ['CGG_CD', 'STDG_CD', 'MNO', 'SNO']].astype(str).agg('|'.join, axis=1).values
    s0['bkey'] = key
    groups = {k: g for k, g in s0.groupby('bkey')}
    ks = list(groups)
    rng = np.random.default_rng(ev['seed'])
    d = []
    for _ in range(500):
        sel = rng.choice(len(ks), len(ks))
        x = pd.concat([groups[ks[j]] for j in sel])
        d.append(100 * (x['rule_err'].median() - x['err'].median()))
    report['stage0_building_bootstrap'] = dict(n_cases=int(len(s0)), n_buildings=len(ks), improvement_pp_mean=round(float(np.mean(d)), 2),
                                               ci95=[round(float(np.percentile(d, 2.5)), 2), round(float(np.percentile(d, 97.5)), 2)])

# ---------------------------------------------------------------- 가격 라벨 (마진 0 / 5 / 10%)
lab = {}
for m in (0.0, 0.05, 0.10):
    L = [eng.label(r['rent'], r, r['grade'], margin=m) for r in V.to_dict('records')]
    ser = pd.Series([x[0] for x in L])
    lab[f'margin_{int(m*100)}'] = ser.value_counts().to_dict()
    V[f'label_m{int(m*100)}'] = ser.values
    V[f'reason_m{int(m*100)}'] = [x[1] for x in L]
report['labels'] = lab
v0, v5 = V['label_m0'], V['label_m5']
report['label_stability'] = dict(
    upper_tail_m0=int((v0 == 'UPPER_TAIL').sum()), upper_tail_retained_m5=int(((v0 == 'UPPER_TAIL') & (v5 == 'UPPER_TAIL')).sum()),
    upper_range_m0=int((v0 == 'UPPER_RANGE').sum()), upper_range_retained_m5=int(((v0 == 'UPPER_RANGE') & (v5 == 'UPPER_RANGE')).sum()),
    unrated_reasons_m5=V[v5 == 'UNRATED']['reason_m5'].value_counts().to_dict())

# ---------------------------------------------------------------- 안전 규칙 위반
viol = []
P = policy['label']
for r in V.to_dict('records'):
    for m in (0.0, 0.05):
        lb = r[f'label_m{int(m*100)}']
        if lb == 'UPPER_TAIL' and (r['usage'] in P['no_tail_usages'] or r['grade'] in P['hold_when_grade'] or r['stage_new'] in P['hold_stage']
                                   or (r['source'] == 'STAGE0' and r['n_use'] < P['strong_label_min_n_stage0'])):
            viol.append(('UPPER_TAIL_FORBIDDEN', r['usage'], r['stage_new']))
        if lb not in ('UNRATED',) and (r['grade'] in P['hold_when_grade'] or r['stage_new'] in P['hold_stage']):
            viol.append(('LABEL_WHEN_HELD', r['usage'], r['stage_new']))
report['safety_violations'] = len(viol)

# ---------------------------------------------------------------- 보고 전용 진단 (통과 기준 아님)
diag = {}
Rb = R.copy()
Rb['gu'] = bases['gu'].values
diag['stage0_reasons_all_bases'] = Rb['stage0_reason'].value_counts().to_dict()
diag['stage0_rate_all_bases_pct'] = round(100 * float((Rb['source'] == 'STAGE0').mean()), 1)
diag['stage0_rate_among_non_detached_pct'] = round(100 * float((Rb[Rb.usage != '단독다가구']['source'] == 'STAGE0').mean()), 1)
diag['stage0_by_usage'] = {u: int((x['source'] == 'STAGE0').sum()) for u, x in Rb.groupby('usage')}
diag['valid_rate_pct'] = round(100 * float(valid.mean()), 1)
diag['rated_rate_m5_pct'] = round(100 * float((V['label_m5'] != 'UNRATED').sum()) / len(R), 1)
diag['by_gu'] = {g: dict(n=int(len(x)), baseline_med=round(M.med_pct(x['rule_err']), 2), v2_med=round(M.med_pct(x['err']), 2),
                         baseline_w20=round(M.within(x['rule_err'].dropna()), 1), v2_w20=round(M.within(x['err']), 1),
                         stage0_n=int((x['source'] == 'STAGE0').sum()), stage_share={int(k): int(v) for k, v in x['stage_new'].value_counts().items()})
                 for g, x in V.assign(gu=bases.loc[V['base_idx'], 'gu'].values).groupby('gu')}
diag['by_stage'] = {int(s): dict(n=int(len(x)), med=round(M.med_pct(x['err']), 2), w20=round(M.within(x['err']), 1)) for s, x in V.groupby('stage_new')}
diag['abs_error_man'] = dict(mae=round(float((V['pred'] - V['rent']).abs().mean()), 2), medae=round(float((V['pred'] - V['rent']).abs().median()), 2),
                             within_3man_pct=round(100 * float(((V['pred'] - V['rent']).abs() <= 3).mean()), 1))
diag['rent_distribution'] = dict(min=float(R['rent'].min()), p5=float(R['rent'].quantile(.05)), median=float(R['rent'].median()),
                                 share_le20_pct=round(100 * float((R['rent'] <= 20).mean()), 1))
s0v = V[V['source'] == 'STAGE0']
if len(s0v):
    inc = s0v['arch_nuniq'] >= 2
    diag['stage0_arch_year_inconsistent'] = dict(n=int(inc.sum()), share_pct=round(100 * float(inc.mean()), 1),
                                                 v2_med_inconsistent=round(M.med_pct(s0v[inc]['err']), 2) if inc.any() else None,
                                                 v2_med_consistent=round(M.med_pct(s0v[~inc]['err']), 2))
report['diagnostics_not_criteria'] = diag

# ---------------------------------------------------------------- 누수 검사
if not a.no_leakage:
    report['leakage'] = LC.run_all(rent, cache, policy, bases, R, quick=a.quick_leakage)
    report['leakage_violations'] = int(sum(x['violations'] for x in report['leakage']))

# ---------------------------------------------------------------- 사전 등록 기준 판정
crit = ev['pass_criteria']
acc = report['accuracy']
checks = {
    'overall_median_err': acc['v2_median_err_pct'] - acc['baseline_median_err_pct'] <= crit['overall_median_err_not_worse_than_pp'],
    'within20_not_lower': acc['v2_within20_pct'] >= acc['baseline_within20_pct'] if crit['within20_not_lower_than_baseline'] else True,
    'grade_monotonic': report['grade_monotonic'],
    'trust_auc': (report.get('trust_scores') or report['trust_scores_loo'])['auc'] >= crit['trust_auc_min'],
    'trust_brier': (report.get('trust_scores') or report['trust_scores_loo'])['brier'] < crit['trust_brier_below'],
    'safety': report['safety_violations'] <= crit['safety_violations'],
    'leakage': report.get('leakage_violations', 0) <= crit['leakage_violations'],
}
hi = [g for g in report['grade_table'] if g['grade'] == '높음']
if hi:
    checks['high_grade_within20_ref_needed'] = None   # 설계 대비 비교는 보고서 작성 시 기준값(설계 88.9%)과 함께 판단
    report['high_grade'] = hi[0]
report['criteria_checks'] = checks

# ---------------------------------------------------------------- 저장
run_id = f'{datetime.now():%Y%m%d_%H%M%S}_{a.label}'
out = INTERNAL / 'results' / run_id
out.mkdir(parents=True, exist_ok=True)
V.drop(columns=['vals0']).to_csv(out / 'records.csv', index=False, encoding='utf-8-sig')
manifest = dict(run_id=run_id, label=a.label, created=datetime.now().isoformat(timespec='seconds'), mode='frozen' if a.frozen else 'design',
                data_file=str(Path(a.data).name), data_sha256=sha256(a.data), data_rows=int(len(rent)),
                building_cache_file=str(CACHE_PATH.name), building_cache_sha256=sha256(CACHE_PATH), building_cache_lots=len(cache),
                policy_file=str(Path(a.policy).name), policy_sha256=pol_hash, policy_version=policy['version'],
                trust_coef_sha256=sha256(coef_path) if coef_path.exists() else None,
                code_version=code_version(), seed=ev['seed'], bases_per_gu=ev['bases_per_gu'], eval_units=int(len(bases)),
                dedupe=policy['stage0']['dedupe_keys'], building_identification=('건축HUB 표제부 주건축물 1동' if policy['stage0']['require_single_building'] else '지번'),
                baseline_check=base_check)
(out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
(out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
print(json.dumps({k: report[k] for k in ('accuracy', 'grade_table', 'grade_monotonic', 'safety_violations', 'criteria_checks')}, ensure_ascii=False, indent=1, default=str))
if 'leakage' in report:
    print('누수 검사:', json.dumps(report['leakage'], ensure_ascii=False))
print('저장:', out)
