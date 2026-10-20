#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전월세 실거래 정제 현황 + 유사 거래 1~3차 탐색 백테스트.
기준 매물(최근 N개월 신규 월세 계약)마다, 그 계약일 이전 거래만 사용해 비교 사례를 찾고
비교 중앙값 월세와 실제 월세를 비교한다(미래 데이터 누수 방지).
실행: python analysis_rent.py data/rent_gwanak_2025_2026.csv
"""
import sys, json
import numpy as np
import pandas as pd
from pathlib import Path

src = Path(sys.argv[1] if len(sys.argv) > 1 else 'data/rent_gwanak_2025_2026.csv')
out = Path('output'); out.mkdir(exist_ok=True)
df = pd.read_csv(src, dtype=str)
n_raw = len(df)

# ---------- 정제 ----------
num = lambda c: pd.to_numeric(df[c], errors='coerce')
df['area'] = num('RENT_AREA'); df['dep'] = num('GRFE'); df['rent'] = num('RTFE')
df['arch'] = num('ARCH_YR'); df['flr'] = num('FLR')
df['date'] = pd.to_datetime(df['CTRT_DAY'], format='%Y%m%d', errors='coerce')
rep = {'전체 건수': n_raw}
rep['월세 계약(RENT_SE=월세)'] = int((df.RENT_SE == '월세').sum())
rep['월세인데 월세금액 0'] = int(((df.RENT_SE == '월세') & (df.rent == 0)).sum())
rep['계약일 해석 불가'] = int(df.date.isna().sum())
rep['건축연도 결측'] = int(df.arch.isna().sum())
rep['신규/갱신 구분 없음'] = int(df.NEW_UPDT_YN.isna().sum())
rep['면적 이상(<5㎡ 또는 >200㎡)'] = int(((df.area < 5) | (df.area > 200)).sum())
rep['월세 이상(>500만원)'] = int((df.rent > 500).sum())
rep['보증금 0'] = int((df.dep == 0).sum())
rep['완전 동일 행 중복'] = int(df.duplicated(subset=[c for c in df.columns if c in
                       ['STDG_CD', 'MNO', 'SNO', 'FLR', 'CTRT_DAY', 'RENT_SE', 'RENT_AREA', 'GRFE', 'RTFE', 'BLDG_NM']]).sum())
rep['층 0(지하 가능성)'] = int((df.flr == 0).sum()); rep['층 음수'] = int((df.flr < 0).sum())
rent = df[(df.RENT_SE == '월세') & df.date.notna() & (df.rent > 0) & (df.area >= 5) & (df.area <= 200) & (df.rent <= 500)].copy()
rent['basement'] = rent.flr <= 0                   # 0·음수층을 지하/반지하 후보로 분리
rep['분석 대상 월세(정제 후)'] = len(rent)
new = rent[rent.NEW_UPDT_YN == '신규']
rep['정제 후 신규 월세'] = len(new)
rep['월세 갱신(제외)'] = int((rent.NEW_UPDT_YN == '갱신').sum()); rep['월세 신규/갱신 불명'] = int(rent.NEW_UPDT_YN.isna().sum())
(out / 'clean_summary.json').write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(rep, ensure_ascii=False, indent=1))
rent.to_csv(out / 'clean_rent_data.csv', index=False, encoding='utf-8-sig')

# ---------- 유사 거래 탐색 ----------
STAGES = [  # 이름, 면적±, 건축연도±, 보증금±(비율), 개월, 지역
    ('1차', 0.10, 5, 0.30, 12, '동'),
    ('2차', 0.20, 10, 0.50, 18, '동'),
    ('3차', 0.25, None, 1.00, 24, '구'),
]
MIN_N = 10
pool = new.sort_values('date').reset_index(drop=True)
base_start = pool.date.max() - pd.DateOffset(months=3)
bases = pool[(pool.date >= base_start)]
bases = bases[bases.STDG_NM == '신림동']
print('기준 매물 수(신림동·최근 3개월 신규 월세):', len(bases))

recs = []
d_arr, dep_arr, area_arr, arch_arr = (pool.date.values, pool.dep.values, pool.area.values, pool.arch.values)
usg_arr, dong_arr, base_arr = pool.BLDG_USG.values, pool.STDG_NM.values, pool.basement.values
rent_arr = pool.rent.values
for i, b in bases.iterrows():
    res = {'idx': i, '용도': b.BLDG_USG, '면적': b.area, '보증금': b.dep, '실제월세': b.rent}
    prior = d_arr < np.datetime64(b.date)
    for name, ap_, ay, dp, months, scope in STAGES:
        lo = np.datetime64(b.date - pd.DateOffset(months=months))
        m = prior & (d_arr >= lo) & (usg_arr == b.BLDG_USG) & (base_arr == b.basement)
        m &= np.abs(area_arr - b.area) <= b.area * ap_
        floor = max(500.0, b.dep * dp)                      # 보증금이 작을 때 비율만으로는 범위가 너무 좁아짐
        m &= np.abs(dep_arr - b.dep) <= (b.dep * dp if b.dep >= 1000 else floor)
        if scope == '동':
            m &= dong_arr == b.STDG_NM
        if ay is not None and not np.isnan(b.arch):
            m &= np.isnan(arch_arr) | (np.abs(arch_arr - b.arch) <= ay)
        cnt = int(m.sum())
        res[f'{name}_건수'] = cnt
        if cnt >= MIN_N and '결정단계' not in res:
            res['결정단계'] = name; res['비교건수'] = cnt
            vals = rent_arr[m]
            res['예측월세'] = float(np.median(vals))
            res['q25'] = float(np.percentile(vals, 25)); res['q75'] = float(np.percentile(vals, 75))
    res.setdefault('결정단계', '보류')
    recs.append(res)
r = pd.DataFrame(recs)
r.to_csv(out / 'similar_search_backtest.csv', index=False, encoding='utf-8-sig')

tab = []
for usg, g in list(r.groupby('용도')) + [('전체', r)]:
    n = len(g)
    row = {'용도': usg, '기준 매물 수': n}
    for s in ['1차', '2차', '3차', '보류']:
        row[f'{s} 결정(%)'] = round(100 * (g['결정단계'] == s).mean(), 1)
    ok = g[g['결정단계'] != '보류']
    if len(ok):
        err = (ok['예측월세'] - ok['실제월세']).abs() / ok['실제월세']
        row['예측 가능 건수'] = len(ok)
        row['중앙 오차율(%)'] = round(100 * err.median(), 1)
        row['오차 ≤10% 비율(%)'] = round(100 * (err <= 0.10).mean(), 1)
        row['오차 ≤20% 비율(%)'] = round(100 * (err <= 0.20).mean(), 1)
        inside = ((ok['실제월세'] >= ok['q25']) & (ok['실제월세'] <= ok['q75'])).mean()
        row['실제값이 IQR 안(%)'] = round(100 * inside, 1)
        row['비교건수 중앙값'] = float(ok['비교건수'].median())
    tab.append(row)
t = pd.DataFrame(tab)
t.to_csv(out / 'similar_search_summary.csv', index=False, encoding='utf-8-sig')
print(t.to_string(index=False))
# 단계별 오차
ok = r[r['결정단계'] != '보류'].copy()
ok['err'] = (ok['예측월세'] - ok['실제월세']).abs() / ok['실제월세']
print(ok.groupby('결정단계')['err'].agg(['count', 'median', lambda x: (x <= 0.2).mean()]).rename(columns={'<lambda_0>': '≤20%'}))
