# -*- coding: utf-8 -*-
"""평가 지표: 신뢰도 로지스틱 적합(구 단위 교차검증)과 요약표. 계산식은 여기 한 곳에서만 정의한다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import np, pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.preprocessing import StandardScaler

GRADES = ['높음', '보통', '낮음']


def med_pct(x):
    x = np.asarray(x, dtype=float)
    return 100 * float(np.nanmedian(x)) if len(x) and np.isfinite(x).any() else float('nan')


def within(x, t=0.2):
    x = pd.Series(x)
    return 100 * float((x <= t).mean())


def fit_trust(df, features, groups='gu'):
    """df: err 가 있는 레코드. 반환 (loo_pred, full_coef_dict). 목표: err<=0.2."""
    y = (df['err'] <= 0.2).astype(int).values
    X = df[features].astype(float)
    loo = np.zeros(len(df))
    for g in df[groups].unique():
        te = (df[groups] == g).values
        sc = StandardScaler().fit(X[~te])
        m = LogisticRegression(max_iter=1000).fit(sc.transform(X[~te]), y[~te])
        loo[te] = m.predict_proba(sc.transform(X[te]))[:, 1]
    sc = StandardScaler().fit(X)
    m = LogisticRegression(max_iter=1000).fit(sc.transform(X), y)
    coef = dict(features=list(features), coef=[float(c) for c in m.coef_[0]], intercept=float(m.intercept_[0]),
                mean=[float(v) for v in sc.mean_], scale=[float(v) for v in sc.scale_], n_train=int(len(df)))
    return loo, coef


def trust_scores(df, p):
    y = (df['err'] <= 0.2).astype(int)
    return dict(auc=float(roc_auc_score(y, p)), brier=float(brier_score_loss(y, p)))


def grade_table(df):
    rows = []
    for g in GRADES:
        x = df[df['grade'] == g]
        if len(x):
            n = len(x)
            k = int((x['err'] <= 0.2).sum())
            p = k / n
            se = (p * (1 - p) / n) ** 0.5
            rows.append(dict(grade=g, n=n, share_pct=round(100 * n / len(df), 1), within20_pct=round(100 * p, 1),
                             ci95=[round(100 * max(p - 1.96 * se, 0), 1), round(100 * min(p + 1.96 * se, 1), 1)],
                             median_err_pct=round(med_pct(x['err']), 2), stage0_share_pct=round(100 * (x['source'] == 'STAGE0').mean(), 1)))
    return rows


def calibration_table(df, p):
    y = (df['err'] <= 0.2).astype(int).values
    rows = []
    for lo, hi in ((0, .3), (.3, .5), (.5, .6), (.6, .7), (.7, .8), (.8, 1.01)):
        m = (p >= lo) & (p < hi)
        if m.sum():
            rows.append(dict(bin=f'{lo:.1f}-{min(hi, 1):.1f}', n=int(m.sum()), predicted_pct=round(100 * float(p[m].mean()), 1), actual_pct=round(100 * float(y[m].mean()), 1)))
    return rows


def is_monotonic(rows, key='within20_pct'):
    v = [r[key] for r in rows]
    return all(a > b for a, b in zip(v, v[1:]))
