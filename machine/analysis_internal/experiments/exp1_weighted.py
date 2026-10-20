# -*- coding: utf-8 -*-
"""실험 1 (설계 6개 구만, 홀드아웃 미사용): (A) 오차 진단, (B) 1~3차 비교군의 유사도 가중 중앙값.
사전 등록(이 파일 상단에 고정):
 - 기준선 = 현재 v2 (0단계 포함). 0단계 사례는 건드리지 않고 RULE(1~3차) 사례의 중앙값만 바꾼다.
 - 비교군(필터)은 기존과 같고, 가중치만 바꾼다: D^2 = u_area^2 + u_dep^2 + u_arch^2 + u_age^2 (각 항은 해당 단계 허용폭으로 정규화), w = exp(-D^2 / (2 h^2)).
 - h 후보 {0.15, 0.25, 0.35, 0.5, 0.75, 1, 1.5, 3, inf} (첫 실행에서 최솟값 0.5 가 모든 폴드에서 선택되어 경계를 넓힘; 첫 실행 기록은 분석결과 28절). 단계(1/2/3)별로 h 를 고르되, 구 단위 중첩 검증: 바깥 구를 빼고 나머지 5개 구에서 중앙 상대오차가 최소인 h 를 골라 바깥 구에 적용.
 - 통과 기준(제안): 전체 중앙 상대오차 v2 대비 0.5%p 이상 개선, 20% 이내 비율 감소 금지, 2·3차 별도 보고, 누수·안전 위반 0(비교군이 기존과 같으므로 누수 경로 변화 없음).
 - 이번에는 중앙값만 바꾼다(가중 Q25/Q75/Q90 과 신뢰도 재학습은 효과 확인 후).
실행: python exp1_weighted.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import ROOT, INTERNAL, np, pd, load_policy, load_rent, load_building_cache, make_bases
from engine_v2 import EngineV2
import compare_rent as cr

policy = load_policy()
rent = load_rent(ROOT / 'output' / 'clean_rent_data.csv')
cache = load_building_cache(ROOT / policy['stage0']['building_cache'])
ev = policy['evaluation']
bases = make_bases(rent, ev['seed'], ev['bases_per_gu'], ev['recent_months'])
eng = EngineV2(rent, cache, policy)
pool = eng.pool

recs = [eng.evaluate(bases.iloc[i]) for i in range(len(bases))]
R = pd.DataFrame(recs)
R['gu'] = bases['gu'].values
R['base_idx'] = np.arange(len(R))
R = R[R['source'] != 'NONE'].copy()
R['abs_err_man'] = (R['pred'] - R['rent']).abs()
R['signed'] = (R['pred'] - R['rent']) / R['rent']

# ================================================================ (A) 진단
print(f'평가 가능 {len(R)}건 | 중앙 상대오차 {100*R.err.median():.2f}% | 20% 이내 {100*(R.err<=.2).mean():.1f}% | MAE {R.abs_err_man.mean():.2f}만 | MedAE {R.abs_err_man.median():.1f}만')
q = R['abs_err_man'].quantile([.5, .75, .9, .95, .99])
print('절대오차(만원) 분위수: 중앙 %.1f / P75 %.1f / P90 %.1f / P95 %.1f / P99 %.1f / 최대 %.0f' % (*q.values, R.abs_err_man.max()))
tot = R['abs_err_man'].sum()
srt = R['abs_err_man'].sort_values(ascending=False)
for pct in (1, 5, 10, 20):
    k = int(len(R) * pct / 100)
    print(f'  오차 상위 {pct}% ({k}건)가 전체 절대오차 합의 {100*srt.head(k).sum()/tot:.1f}%')
print('월세 구간별:')
R['band'] = pd.cut(R['rent'], [0, 30, 60, 100, 10 ** 6], labels=['<=30', '30~60', '60~100', '>100'])
for b, x in R.groupby('band', observed=True):
    print(f'  {b:>6}: n={len(x):5d} ({100*len(x)/len(R):4.1f}%) | 중앙 상대 {100*x.err.median():5.1f}% | MAE {x.abs_err_man.mean():5.1f}만 | 합 기여 {100*x.abs_err_man.sum()/tot:4.1f}% | 부호 중앙 {100*x.signed.median():+5.1f}% | 과소예측 비율 {100*(x.signed<0).mean():4.1f}%')
print('유형 x 단계 (n, 중앙 상대, MAE, 절대오차 합 기여%):')
for (u, s), x in R.groupby(['usage', 'stage_new']):
    print(f'  {u} 단계{int(s)}: n={len(x):5d} {100*x.err.median():5.1f}% MAE {x.abs_err_man.mean():5.1f}만 기여 {100*x.abs_err_man.sum()/tot:4.1f}%')
print('단계별 절대오차 합 기여:', {int(s): f'{100*x.abs_err_man.sum()/tot:.1f}% (n={len(x)})' for s, x in R.groupby('stage_new')})
five = (R['rent'] % 5 == 0).mean()
print(f'월세가 5의 배수인 비율 {100*five:.1f}%')

# ================================================================ (B) 유사도 가중 중앙값
H_LIST = [0.15, 0.25, 0.35, 0.5, 0.75, 1.0, 1.5, 3.0, np.inf]
STG = {int(s['name'][0]): s for s in cr.STAGES}


def wmedian(v, w):
    o = np.argsort(v, kind='stable')
    v, w = v[o], w[o]
    c = np.cumsum(w)
    return float(v[np.searchsorted(c, 0.5 * c[-1])])


def candidates(i):
    b = bases.iloc[i]
    L = dict(gu=b['gu'], dong=b['dong'], usage=b['usage'], area=float(b['area']), deposit=float(b['dep']), rent=float(b['rent']),
             arch_year=None if pd.isna(b['arch']) else float(b['arch']), basement=bool(b['basement']))
    as_of = np.datetime64(pd.Timestamp(b['date']), 'D')
    return L, as_of


rule = R[R['source'] == 'RULE'].copy()
rows = []
for _, r in rule.iterrows():
    L, as_of = candidates(int(r['base_idx']))
    st = STG[int(r['stage_new'])]
    arr = pool.get(st['scope'], L['gu'], L['dong'], L['usage'], L['basement'])
    m, arr = cr._select(arr, L, as_of, st)
    v = arr['rent'][m].astype(float)
    area = arr['area'][m]
    dep = arr['dep'][m]
    arch = arr['arch'][m]
    age = (as_of - arr['date'][m]).astype('timedelta64[D]').astype(float)
    u_area = np.abs(np.log(area / L['area'])) / np.log(1 + st['area'])
    band = L['deposit'] * st['dep'] if L['deposit'] >= 1000 else max(cr.DEP_FLOOR, L['deposit'] * st['dep'])
    u_dep = np.abs(dep - L['deposit']) / band
    if st['arch'] is not None and L['arch_year'] is not None:
        u_arch = np.where(np.isnan(arch), 0.5, np.abs(arch - L['arch_year']) / st['arch'])
    else:
        u_arch = np.zeros(len(v))
    u_age = age / (st['months'] * 30.4375)
    D2 = u_area ** 2 + u_dep ** 2 + u_arch ** 2 + u_age ** 2
    row = dict(base_idx=int(r['base_idx']), gu=r['gu'], stage=int(r['stage_new']), usage=r['usage'], rent=r['rent'], base_pred=r['pred'],
               n=len(v), unweighted_check=float(np.median(v)))
    for h in H_LIST:
        w = np.ones(len(v)) if np.isinf(h) else np.exp(-D2 / (2 * h * h))
        row[f'p_{h}'] = wmedian(v, w)
        row[f'neff_{h}'] = float(w.sum() ** 2 / (w ** 2).sum())
    rows.append(row)
W = pd.DataFrame(rows)
print(f'\n=== (B) 가중 중앙값: RULE 사례 {len(W)}건 ===')
print('기존 중앙값과 재계산 일치(h=inf 가중중앙값 vs np.median, 상대 차 평균): %.4f%%' % (100 * ((W['p_inf'] - W['unweighted_check']).abs() / W['rent']).mean()))
for h in H_LIST:
    W[f'e_{h}'] = (W[f'p_{h}'] - W['rent']).abs() / W['rent']
W['e_base'] = (W['base_pred'] - W['rent']).abs() / W['rent']
print('h 별 중앙 상대오차(전체 RULE / 1차 / 2차 / 3차) 와 평균 유효표본수:')
print(f'  기존(np.median)  : {100*W.e_base.median():.2f} / ' + ' / '.join(f'{100*W[W.stage==s].e_base.median():.2f}' for s in (1, 2, 3)))
for h in H_LIST:
    print(f'  h={h:<5}         : {100*W[f"e_{h}"].median():.2f} / ' + ' / '.join(f'{100*W[W.stage==s][f"e_{h}"].median():.2f}' for s in (1, 2, 3))
          + f' | n_eff 중앙 {W[f"neff_{h}"].median():.1f} (n 중앙 {W.n.median():.0f})')

# --- 구 단위 중첩 선택
print('\n=== 중첩 구 교차검증: 바깥 구 제외 후 단계별 h 선택 ===')
chosen = {}
W['p_sel'] = np.nan
for g in sorted(W['gu'].unique()):
    te = (W['gu'] == g)
    for s in (1, 2, 3):
        tr = W[(~te) & (W.stage == s)]
        best = min(H_LIST, key=lambda h: tr[f'e_{h}'].median())
        chosen[(g, s)] = best
        idx = W[te & (W.stage == s)].index
        W.loc[idx, 'p_sel'] = W.loc[idx, f'p_{best}']
print('선택된 h:', {f'{g}/{s}차': h for (g, s), h in chosen.items()})
W['e_sel'] = (W['p_sel'] - W['rent']).abs() / W['rent']
print(f'RULE 사례 중앙 상대오차: 기존 {100*W.e_base.median():.2f}% -> 가중(중첩 선택) {100*W.e_sel.median():.2f}% | 20% 이내 {100*(W.e_base<=.2).mean():.1f}% -> {100*(W.e_sel<=.2).mean():.1f}%')
for s in (1, 2, 3):
    x = W[W.stage == s]
    print(f'  {s}차 (n={len(x)}): {100*x.e_base.median():.2f}% -> {100*x.e_sel.median():.2f}% | 20% 이내 {100*(x.e_base<=.2).mean():.1f}% -> {100*(x.e_sel<=.2).mean():.1f}%')
print('  유형별 (기존 -> 가중):')
for u, x in W.groupby('usage'):
    print(f'    {u}: n={len(x)} {100*x.e_base.median():.2f}% -> {100*x.e_sel.median():.2f}%')
print('  구별 (기존 -> 가중):')
for g, x in W.groupby('gu'):
    print(f'    {g}: n={len(x)} {100*x.e_base.median():.2f}% -> {100*x.e_sel.median():.2f}%')

# 전체 시스템(0단계 유지) 환산
R2 = R.copy()
R2['final_err'] = R2['err']
m = W.set_index('base_idx')['e_sel']
mask = R2['base_idx'].isin(m.index)
R2.loc[mask, 'final_err'] = R2.loc[mask, 'base_idx'].map(m).values
print(f'\n전체 시스템({len(R2)}건, 0단계 유지): 중앙 상대오차 {100*R.err.median():.2f}% -> {100*R2.final_err.median():.2f}% | 20% 이내 {100*(R.err<=.2).mean():.1f}% -> {100*(R2.final_err<=.2).mean():.1f}%')
MAE0 = R['abs_err_man'].mean()
MAE1 = np.where(mask, (R2['base_idx'].map(W.set_index('base_idx')['p_sel']) - R2['rent']).abs(), R2['abs_err_man']).mean()
print(f'평균 절대오차 {MAE0:.2f}만 -> {MAE1:.2f}만')
# 사례 단위 부트스트랩 (개선폭 신뢰구간)
rng = np.random.default_rng(0)
a, b_ = R['err'].values, R2['final_err'].values
d = []
for _ in range(500):
    s = rng.integers(0, len(a), len(a))
    d.append(100 * (np.median(a[s]) - np.median(b_[s])))
print(f'전체 개선폭 부트스트랩(사례 단위, 건물 군집 미반영): {np.mean(d):.2f}%p, 95% [{np.percentile(d,2.5):.2f}, {np.percentile(d,97.5):.2f}]')

out = INTERNAL / 'results' / f'exp1_weighted_{datetime.now():%Y%m%d_%H%M%S}.json'
out.write_text(json.dumps(dict(n_rule=len(W), base_overall_med=float(R.err.median()), new_overall_med=float(R2.final_err.median()),
                               chosen={f'{g}/{s}': h for (g, s), h in chosen.items()}), ensure_ascii=False, indent=1, default=str), encoding='utf-8')
W.to_csv(INTERNAL / 'results' / 'exp1_weighted_cases.csv', index=False, encoding='utf-8-sig')
print('저장:', out)
