#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""가짜 결측 실험: 층을 아는 연립다세대에서 층 정보를 가려 '단독다가구와 비슷한 상황'을 만들고 정책을 비교한다.

정답(oracle): 같은 층 유형(지하/지상)끼리만 비교한 분포로 만든 라벨.
가림(masked): 지하·지상을 섞은 비교군(단독다가구 현재 상태). 지하 비율 p 는 가중치로 바꿔 가며 시험.
높은 가격대 라벨 = 월세 > 비교군 Q75, 강한 라벨 = 월세 > Q90.
정책: C-lite  = 가림 분포 기준 Q75 초과이면 "높은 편" 허용
      F(+s)   = 가림 분포를 s 만큼 비싸게 보정해도(= Q75×(1+s)) 초과여야 허용 (판정 안정성 규칙)
평가: 정답과 다르게 "높은 편"이라고 한 비율(오경고율 FDR = 1-정밀도), 정답이 높은 편인 매물을 잡아낸 비율(재현율), 경고 건수.
한계: 연립다세대와 단독다가구는 다른 집단이고, 기준 매물의 지하 비율은 실제로 ~3%라 p 를 가중치로 인위 조정함.
실행: python fake_missing_floor.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
OUT = HERE / 'output'
rent = pd.read_csv(OUT / 'clean_rent_data.csv', parse_dates=['date'], low_memory=False)
mu = rent[(rent['usage'] == '연립다세대') & rent['is_new'].astype(bool) & ((rent['flr'] < 0) | (rent['flr'] >= 1))].sort_values('date').reset_index(drop=True)
mu['is_b'] = mu['flr'] < 0
d = mu['date'].values.astype('datetime64[D]'); area = mu['area'].values; dep = mu['dep'].values
arch = mu['arch'].values; rentv = mu['rent'].values; isb = mu['is_b'].values
dong = mu['dong'].values; gu = mu['gu'].values
by_dong = {k: np.array(v) for k, v in mu.groupby(['gu', 'dong']).indices.items()}

STAGES = [(0.10, 5, 0.30, 12), (0.20, 10, 0.50, 18)]       # 1·2차만(3차는 정책상 판정 보류)
bases = mu[mu['date'] >= mu['date'].max() - pd.Timedelta(days=92)].index.values
print('기준 매물(연립다세대 신규, 최근 3개월):', len(bases), '| 그중 지하', int(isb[bases].sum()))


def wq(x, w, qs):
    o = np.argsort(x); x = x[o]; w = w[o]; c = np.cumsum(w) / w.sum()
    return [float(x[min(np.searchsorted(c, q), len(x) - 1)]) for q in qs]


recs = []
for i in bases:
    idx = by_dong[(gu[i], dong[i])]
    idx = idx[d[idx] < d[i]]
    for st, (ar, ay, dp, mo) in enumerate(STAGES, 1):
        m = idx[(d[idx] >= d[i] - np.timedelta64(int(mo * 30.4375), 'D'))]
        m = m[np.abs(area[m] - area[i]) <= area[i] * ar]
        band = dep[i] * dp if dep[i] >= 1000 else max(500.0, dep[i] * dp)
        m = m[np.abs(dep[m] - dep[i]) <= band]
        if not np.isnan(arch[i]):
            m = m[np.isnan(arch[m]) | (np.abs(arch[m] - arch[i]) <= ay)]
        orc = m[isb[m] == isb[i]]
        if len(m) >= 10 and len(orc) >= 10:
            nb = int(isb[m].sum()); ng = len(m) - nb
            recs.append(dict(i=i, stage=st, actual=rentv[i], base_b=bool(isb[i]), n_mixed=len(m), n_b=nb, n_g=ng, n_orc=len(orc),
                             o_q75=float(np.percentile(rentv[orc], 75)), o_q90=float(np.percentile(rentv[orc], 90)),
                             mixed_idx=m))
            break
R = pd.DataFrame(recs)
print('1·2차에서 정답/가림 비교군이 모두 10건 이상인 매물:', len(R), '| 지상', int((~R.base_b).sum()), '지하', int(R.base_b.sum()))
print('비교군 안의 지하 비율 분포(자연): 중앙 %.1f%%, 평균 %.1f%%' % (100 * (R.n_b / R.n_mixed).median(), 100 * (R.n_b / R.n_mixed).mean()))

P_LIST = [None, 0.10, 0.20, 0.30, 0.50]
POLICIES = [('C-lite: Q75 초과', 0.0, 'q75'), ('F(+5%): Q75×1.05 초과', 0.05, 'q75'), ('F(+10%): Q75×1.10 초과', 0.10, 'q75'),
            ('F(+15%): Q75×1.15 초과', 0.15, 'q75'), ('강한 라벨: Q90 초과', 0.0, 'q90')]
rows = []
for p in P_LIST:
    sub = R if p is None else R[R.n_b >= 3]           # 지하 비교 사례가 3건 이상 있어야 p 가중치를 줄 수 있음
    for grp, g in (('지상 매물', sub[~sub.base_b]), ('지하 매물', sub[sub.base_b])):
        if len(g) < 20:
            continue
        flag = {pol[0]: [] for pol in POLICIES}
        truth_hi, truth_strong = [], []
        for r in g.itertuples():
            m = r.mixed_idx
            w = np.ones(len(m))
            if p is not None:
                wb = (p / (1 - p)) * (r.n_g / r.n_b)
                w = np.where(isb[m], wb, 1.0)
            q75, q90 = wq(rentv[m], w, [0.75, 0.90])
            truth_hi.append(r.actual > r.o_q75); truth_strong.append(r.actual > r.o_q90)
            for name, sh, qq in POLICIES:
                thr = (q75 if qq == 'q75' else q90) * (1 + sh)
                flag[name].append(r.actual > thr)
        th = np.array(truth_hi); ts = np.array(truth_strong)
        for name, sh, qq in POLICIES:
            f = np.array(flag[name]); t = ts if qq == 'q90' else th
            tp = int((f & t).sum()); fp = int((f & ~t).sum()); fn = int((~f & t).sum())
            rows.append({'지하 비율 p': '자연(실제)' if p is None else f'{int(p*100)}%', '대상': grp, '정책': name, '매물 수': len(g),
                         '경고 건수': int(f.sum()), '경고율(%)': round(100 * f.mean(), 1),
                         '오경고율 FDR(%)': round(100 * fp / max(tp + fp, 1), 1), '재현율(%)': round(100 * tp / max(tp + fn, 1), 1),
                         '정답 높은 편 비율(%)': round(100 * t.mean(), 1)})
res = pd.DataFrame(rows)
res.to_csv(OUT / 'fake_missing_floor_results.csv', index=False, encoding='utf-8-sig')
pd.set_option('display.width', 250)
for p in res['지하 비율 p'].unique():
    for grp in ('지상 매물', '지하 매물'):
        t = res[(res['지하 비율 p'] == p) & (res['대상'] == grp)]
        if len(t):
            print(f'\n== p={p} | {grp} | 매물 {t["매물 수"].iloc[0]}건 | 정답 기준 높은 편 비율(Q75 초과) {t[t["정책"].str.startswith("C-lite")]["정답 높은 편 비율(%)"].iloc[0]}%')
            print(t[['정책', '경고 건수', '경고율(%)', '오경고율 FDR(%)', '재현율(%)']].to_string(index=False))
