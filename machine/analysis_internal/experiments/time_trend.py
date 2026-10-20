# -*- coding: utf-8 -*-
"""시점 추세 민감도 — 설계 6개 구. 외부 지수 없이 우리 데이터의 구성 보정 월별 지수를 만들어 오래된 비교 거래의 가격 수준을 보정해 본다.
1) 월별 진단: 월별 부호 있는 오차 (예측-실제)/실제, 실제 월세가 Q90 초과인 비율
2) 보정 효과: 평가 시점 이전(신고 지연 30일 반영)에 관측된 추세 기울기로 예측/분위수를 스케일 -> 오차·편향·Q90 초과율 비교
추세 보정 계수 = exp(lambda * slope_per_month * age_months), age = 비교 창의 평균 연령(0단계 12개월, 1차 6, 2차 9, 3차 12), lambda in {0, 0.5, 1}.
지수: log(월세) ~ (구×용도) 고정효과 + log(면적) + log(보증금+100) + 월 더미 (신규 계약, 평가월 시작 30일 전까지 데이터, 완결 월만).
실행: python time_trend.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import ROOT, INTERNAL, np, pd, load_policy, load_rent, load_building_cache
from engine_v2 import EngineV2

policy = load_policy()
rent = load_rent(ROOT / 'output' / 'clean_rent_data.csv')
cache = load_building_cache(ROOT / policy['stage0']['building_cache'])
new = rent[rent['is_new']].copy()
print('신규 계약', len(new), '기간', new['date'].min().date(), '~', new['date'].max().date())

# ------------------------------------------------------------------ 평가 표본: 월별·구별 무작위
rng = np.random.default_rng(11)
new['ym'] = new['date'].dt.to_period('M')
months = [m for m in sorted(new['ym'].unique()) if m >= pd.Period('2025-07') and m <= new['ym'].max()]
parts = []
for m in months:
    for gu, g in new[new['ym'] == m].groupby('gu'):
        parts.append(g.sample(min(120, len(g)), random_state=int(rng.integers(1e9))))
bases = pd.concat(parts).reset_index(drop=True)
print('평가 표본', len(bases), '월', len(months))
eng = EngineV2(rent, cache, policy)
R = pd.DataFrame([eng.evaluate(r) for _, r in bases.iterrows()])
R['ym'] = bases['ym'].values
R = R[R['source'] != 'NONE'].copy()
R['signed'] = (R['pred'] - R['rent']) / R['rent']
R['q90x'] = R['rent'] > R['q90']
R['age_m'] = np.where(R['source'] == 'STAGE0', 12.0, R['stage_new'].map({1: 6.0, 2: 9.0, 3: 12.0}))
print(f'평가 가능 {len(R)}건 / 0단계 {int((R.source=="STAGE0").sum())}건')

# ------------------------------------------------------------------ 1) 월별 진단
print('\n=== (1) 월별 진단 (예측-실제)/실제 중앙값, 중앙 절대오차, 실제가 Q90 초과 비율 ===')
tab = R.groupby('ym').agg(n=('err', 'size'), signed_med=('signed', 'median'), abs_med=('err', 'median'), q90x=('q90x', 'mean')).reset_index()
tab['signed_med'] = (100 * tab['signed_med']).round(1)
tab['abs_med'] = (100 * tab['abs_med']).round(1)
tab['q90x'] = (100 * tab['q90x']).round(1)
print(tab.to_string(index=False))
print('전체: 부호 중앙값 %.1f%%, 중앙 절대오차 %.2f%%, Q90 초과 %.1f%%' % (100 * R.signed.median(), 100 * R.err.median(), 100 * R.q90x.mean()))
for s, x in R.groupby('stage_new'):
    print(f'  단계 {int(s)}: n={len(x)} 부호 중앙값 {100*x.signed.median():+.1f}% / 중앙 절대오차 {100*x.err.median():.1f}% / Q90 초과 {100*x.q90x.mean():.1f}%')

# ------------------------------------------------------------------ 2) 월별 지수와 추세
new['mi'] = (new['date'].dt.year - 2025) * 12 + new['date'].dt.month - 1
new['lr'] = np.log(new['rent'])
new['la'] = np.log(new['area'])
new['ld'] = np.log(new['dep'] + 100)
new['grp'] = new['gu'] + '|' + new['usage']
grp_codes = {g: i for i, g in enumerate(sorted(new['grp'].unique()))}
new['gi'] = new['grp'].map(grp_codes)
ng = len(grp_codes)


def fit_index(upto_month_idx_inclusive):
    """완결 월(<= upto)까지의 데이터로 월 효과 추정. 반환 {월인덱스: 로그 지수}"""
    d = new[new['mi'] <= upto_month_idx_inclusive]
    ms = sorted(d['mi'].unique())
    base_m = ms[0]
    cols_m = ms[1:]
    X = np.zeros((len(d), ng + 2 + len(cols_m)))
    X[np.arange(len(d)), d['gi'].values] = 1.0
    X[:, ng] = d['la'].values
    X[:, ng + 1] = d['ld'].values
    for j, m in enumerate(cols_m):
        X[:, ng + 2 + j] = (d['mi'].values == m).astype(float)
    beta, *_ = np.linalg.lstsq(X, d['lr'].values, rcond=None)
    idx = {base_m: 0.0}
    for j, m in enumerate(cols_m):
        idx[m] = float(beta[ng + 2 + j])
    return idx


def slope_for(month_period, lag_days=30, trail=6):
    """평가월 시작 lag_days 전까지의 완결 월 지수의 최근 trail개월 기울기(로그/월)."""
    start = month_period.to_timestamp()
    cutoff = start - pd.Timedelta(days=lag_days)
    last_full = (cutoff.year - 2025) * 12 + cutoff.month - 1 - 1     # cutoff 가 속한 달은 불완전 -> 직전 달까지
    idx = fit_index(last_full)
    ks = sorted(idx)[-trail:]
    if len(ks) < 3:
        return 0.0, idx
    return float(np.polyfit(np.arange(len(ks)), [idx[k] for k in ks], 1)[0]), idx


slopes = {}
print('\n=== (2) 월별 지수 기울기 (평가월 시작 30일 전까지 관측, 최근 6개월 로그/월) ===')
for m in months:
    sl, idx = slope_for(m)
    slopes[m] = sl
print(pd.DataFrame({'월': [str(m) for m in months], '추세(월 %)': [round(100 * slopes[m], 2) for m in months]}).T.to_string(header=False))

# ------------------------------------------------------------------ 3) 보정 효과
R['slope'] = R['ym'].map(slopes)
print('\n=== (3) 추세 보정 효과 (lambda = 보정 강도) ===')
rows = []
for lam in (0.0, 0.5, 1.0):
    f = np.exp(lam * R['slope'] * R['age_m'])
    p = R['pred'] * f
    q90 = R['q90'] * f
    err = (p - R['rent']).abs() / R['rent']
    sgn = (p - R['rent']) / R['rent']
    rows.append(dict(lam=lam, 중앙오차=round(100 * err.median(), 2), 오차20이내=round(100 * (err <= .2).mean(), 1), 부호중앙=round(100 * sgn.median(), 2),
                     Q90초과=round(100 * (R['rent'] > q90).mean(), 1)))
print(pd.DataFrame(rows).to_string(index=False))
print('  단계별(lambda 0 -> 1) 중앙오차/부호:')
for s, x in R.groupby('stage_new'):
    out = []
    for lam in (0.0, 1.0):
        f = np.exp(lam * x['slope'] * x['age_m'])
        p = x['pred'] * f
        out.append(f'{100*((p-x.rent).abs()/x.rent).median():.1f}%/{100*((p-x.rent)/x.rent).median():+.1f}%')
    print(f'   단계 {int(s)} (n={len(x)}): {out[0]} -> {out[1]}')
print('  월별 일관성(lambda=1 이 lambda=0 보다 중앙 절대오차가 낮은 달 수):')
better = 0
for m, x in R.groupby('ym'):
    e0 = ((x.pred - x.rent).abs() / x.rent).median()
    f = np.exp(x['slope'] * x['age_m'])
    e1 = (((x.pred * f) - x.rent).abs() / x.rent).median()
    better += int(e1 < e0)
print(f'   {better} / {R.ym.nunique()}')
R.drop(columns=['vals0']).to_csv(INTERNAL / 'results' / 'time_trend_records.csv', index=False, encoding='utf-8-sig')
