#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 월세 함정 탐지기 - 분석 모듈 (데이터 정제 + 유사 실거래 탐색 + 신뢰도).

백엔드/프론트가 호출하는 진입점은 compare(listing, pool).
  listing = {'gu':'관악구','dong':'신림동','usage':'단독다가구','area':24.0,'deposit':1000,'rent':50,
             'arch_year':2015(선택), 'basement':False(선택), 'as_of':'2026-10-18'(선택)}
단위: area ㎡, deposit·rent 만원.

설계 원칙
- 비교 대상은 '신규' 월세 계약만(갱신 제외). 같은 용도·같은 지하 여부끼리만 비교.
- 비교 사례가 MIN_N(10) 미만이면 1차 -> 2차 -> 3차로 조건을 완화하고, 그래도 부족하면 판단 보류.
- as_of 이전 계약만 사용(미래 데이터 누수 방지).
- 시세 판단은 중앙값 하나가 아니라 사분위 범위(IQR)와 백분위로 함께 제시하고, 신뢰도가 낮으면 판정하지 않는다.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

USAGES = ('단독다가구', '연립다세대', '오피스텔', '아파트')
MIN_N = 10
DEP_FLOOR = 500          # 보증금이 작은 계약(<1,000만원)은 비율 대신 ±500만원 범위
CONV_RATE = 0.0          # 보증금 차이를 월세로 환산하는 연 전환율(0이면 환산 안 함). run_validation 결과로 정함.
STAGES = [
    dict(name='1차', area=0.10, arch=5, dep=0.30, months=12, scope='dong'),
    dict(name='2차', area=0.20, arch=10, dep=0.50, months=18, scope='dong'),
    dict(name='3차', area=0.25, arch=None, dep=1.00, months=24, scope='gu'),
]
FIT_BASE = {'1차': 100, '2차': 70, '3차': 40}


# ------------------------------------------------------------------ 정제
def clean(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """서울시 전월세가 원본(문자열 DataFrame) -> 분석용 월세 DataFrame, 정제 요약."""
    df = df_raw.copy()
    n = pd.to_numeric
    df['area'] = n(df['RENT_AREA'], errors='coerce')
    df['dep'] = n(df['GRFE'], errors='coerce')
    df['rent'] = n(df['RTFE'], errors='coerce')
    df['arch'] = n(df['ARCH_YR'], errors='coerce')
    df['flr'] = n(df['FLR'], errors='coerce')
    df['date'] = pd.to_datetime(df['CTRT_DAY'], format='%Y%m%d', errors='coerce')
    df['gu'] = df['CGG_NM']; df['dong'] = df['STDG_NM']; df['usage'] = df['BLDG_USG']
    # 단독다가구는 층 값이 전부 0 -> 지하 여부를 알 수 없음. 층 < 0 일 때만 지하로 본다.
    df['basement'] = df['flr'] < 0
    df['is_new'] = df['NEW_UPDT_YN'] == '신규'
    rep = {'전체': len(df)}
    month = df['RENT_SE'] == '월세'
    rep['월세'] = int(month.sum())
    ok = month & df['date'].notna() & (df['rent'] > 0) & (df['rent'] <= 500) & (df['area'] >= 5) & (df['area'] <= 200) & (df['dep'] >= 0)
    ok &= df['usage'].isin(USAGES)
    rep['월세인데 월세 0원'] = int((month & (df['rent'] <= 0)).sum())
    rep['면적 이상(<5 또는 >200㎡)'] = int((month & ((df['area'] < 5) | (df['area'] > 200))).sum())
    rep['월세 500만원 초과'] = int((month & (df['rent'] > 500)).sum())
    rep['건축연도 결측(월세)'] = int((month & df['arch'].isna()).sum())
    rep['정제 후 월세'] = int(ok.sum())
    out = df[ok].copy()
    # 신규/갱신 내역은 모두 '정제 후 월세' 기준으로 계산 -> 세 항목의 합이 정제 후 월세와 정확히 일치
    rep['  정제 후 신규(비교 풀)'] = int(out['is_new'].sum())
    rep['  정제 후 갱신(비교 제외)'] = int((out['NEW_UPDT_YN'] == '갱신').sum())
    rep['  정제 후 신규/갱신 불명(비교 제외)'] = int(out['NEW_UPDT_YN'].isna().sum())
    assert rep['  정제 후 신규(비교 풀)'] + rep['  정제 후 갱신(비교 제외)'] + rep['  정제 후 신규/갱신 불명(비교 제외)'] == rep['정제 후 월세']
    rep['제거된 월세(정제 전→후)'] = rep['월세'] - rep['정제 후 월세']
    keycols = ['dong', 'MNO', 'SNO', 'flr', 'CTRT_DAY', 'area', 'dep', 'rent', 'BLDG_NM', 'usage']
    rep['동일 행 중복 의심(삭제하지 않음)'] = int(out.duplicated(subset=keycols).sum())
    out['dup_suspect'] = out.duplicated(subset=keycols, keep=False)
    return out.reset_index(drop=True), rep


# ------------------------------------------------------------------ 비교 풀
class Pool:
    """신규 월세 계약을 (구, 용도, 지하여부[, 동]) 그룹별 numpy 배열로 보관."""

    def __init__(self, rent: pd.DataFrame):
        new = rent[rent['is_new']].sort_values('date')
        self.max_date = new['date'].max()
        self._g_gu, self._g_dong = {}, {}
        cols = ['date', 'area', 'dep', 'rent', 'arch']
        for key, g in new.groupby(['gu', 'usage', 'basement']):
            self._g_gu[key] = {c: (g[c].values if c != 'date' else g[c].values.astype('datetime64[D]')) for c in cols}
        for key, g in new.groupby(['gu', 'dong', 'usage', 'basement']):
            self._g_dong[key] = {c: (g[c].values if c != 'date' else g[c].values.astype('datetime64[D]')) for c in cols}

    def get(self, scope, gu, dong, usage, basement):
        if scope == 'dong':
            return self._g_dong.get((gu, dong, usage, basement))
        return self._g_gu.get((gu, usage, basement))


# ------------------------------------------------------------------ 비교
def _select(arr, L, as_of, st):
    if arr is None:
        return np.zeros(0, bool), None
    lo = as_of - np.timedelta64(int(round(st['months'] * 30.4375)), 'D')
    m = (arr['date'] < as_of) & (arr['date'] >= lo)
    m &= np.abs(arr['area'] - L['area']) <= L['area'] * st['area']
    dep = L['deposit']
    band = dep * st['dep'] if dep >= 1000 else max(DEP_FLOOR, dep * st['dep'])
    m &= np.abs(arr['dep'] - dep) <= band
    if st['arch'] is not None and L.get('arch_year') is not None:
        m &= np.isnan(arr['arch']) | (np.abs(arr['arch'] - L['arch_year']) <= st['arch'])
    return m, arr


def _trust(stage, n, rent_vals, dates, as_of, L):
    fit = FIT_BASE[stage]
    fit_notes = []
    if L['usage'] == '단독다가구':
        fit -= 10; fit_notes.append('단독다가구는 층(반지하) 구분 불가')
    if L['usage'] == '연립다세대':
        # 6개 구 백테스트에서 연립다세대 중앙 오차가 24~28%로 다른 용도(7~16%)보다 컸음(건물·호실 편차)
        fit -= 15; fit_notes.append('연립다세대는 건물·호실 편차가 커 비교 오차가 큼')
    if L.get('arch_year') is None:
        fit -= 10; fit_notes.append('건축연도 미입력')
    suff = min(n / 30, 1) * 60
    recent = float(np.mean(dates >= as_of - np.timedelta64(183, 'D')))
    suff += recent * 20
    med = float(np.median(rent_vals))
    rel_iqr = float((np.percentile(rent_vals, 75) - np.percentile(rent_vals, 25)) / med) if med > 0 else 9
    suff += 20 if rel_iqr <= 0.25 else (10 if rel_iqr <= 0.40 else 0)
    if fit >= 70 and suff >= 70:
        grade = '높음'
    elif fit >= 50 and suff >= 50:
        grade = '보통'
    else:
        grade = '낮음'
    return dict(fit=round(fit), sufficiency=round(suff), grade=grade, recent_share=round(recent, 2),
                rel_iqr=round(rel_iqr, 2), notes=fit_notes)


def compare(listing: dict, pool: Pool, as_of=None, conv_rate: float | None = None) -> dict:
    L = dict(listing)
    usage = L['usage']
    basement = bool(L.get('basement', False))
    as_of = np.datetime64(pd.Timestamp(as_of or L.get('as_of') or (pool.max_date + pd.Timedelta(days=1))), 'D')
    conv = CONV_RATE if conv_rate is None else conv_rate
    trace = []
    chosen = None
    for st in STAGES:
        arr = pool.get(st['scope'], L['gu'], L['dong'], usage, basement)
        m, arr = _select(arr, L, as_of, st)
        n = int(m.sum())
        trace.append({'stage': st['name'], 'n': n})
        if n >= MIN_N:
            chosen = (st, m, arr, n)
            break
    if chosen is None:
        return dict(status='보류', stage=None, n=trace[-1]['n'], trace=trace,
                    message='비교 가능한 실거래가 부족해 시세 판단을 보류합니다. 조건을 완화해도 비교 사례가 %d건 미만입니다.' % MIN_N,
                    trust=dict(grade='보류'))
    st, m, arr, n = chosen
    adj = arr['rent'][m] + (arr['dep'][m] - L['deposit']) * conv / 12.0
    adj = np.maximum(adj, 1.0)          # 보증금 환산으로 월세가 0 이하가 되는 극단값 방지
    med = float(np.median(adj)); q25 = float(np.percentile(adj, 25)); q75 = float(np.percentile(adj, 75))
    q10 = float(np.percentile(adj, 10)); q90 = float(np.percentile(adj, 90))
    # 월세는 50·60만원처럼 딱 떨어지는 값에 몰려 동점이 많음 -> 중간 순위(mid-rank) 백분위로 계산
    pct = float(np.mean(adj < L['rent']) + 0.5 * np.mean(adj == L['rent']))
    trust = _trust(st['name'], n, adj, arr['date'][m], as_of, L)
    if trust['grade'] == '낮음':
        verdict = '참고만(신뢰도 낮음)'
    elif L['rent'] > q90:
        verdict = '비싼 편(상위 10%)'
    elif L['rent'] > q75:
        verdict = '다소 높음(상위 25%)'
    elif L['rent'] < q25:
        verdict = '낮은 편(하위 25%)'
    else:
        verdict = '시세 범위(중간 50%)'
    return dict(status='ok', stage=st['name'], n=n, median=round(med, 1), q25=round(q25, 1), q75=round(q75, 1),
                q10=round(q10, 1), q90=round(q90, 1), percentile=round(pct, 3),
                diff_man=round(L['rent'] - med, 1), diff_pct=round((L['rent'] - med) / med, 3),
                verdict=verdict, trust=trust, trace=trace,
                relaxed=[s['name'] for s in STAGES if s['name'] != '1차' and s['name'] <= st['name']],
                message='비교 %d건(%s) 기준 시세 중앙값 %.0f만원, 중간 50%% 범위 %.0f~%.0f만원' % (n, st['name'], med, q25, q75))


# ------------------------------------------------------------------ 백테스트
def backtest(pool: Pool, bases: pd.DataFrame, conv_rate: float | None = None) -> pd.DataFrame:
    """bases의 각 계약을 '그 계약일 이전 거래만 있는 상태'에서 평가."""
    rows = []
    for r in bases.itertuples(index=False):
        L = dict(gu=r.gu, dong=r.dong, usage=r.usage, area=float(r.area), deposit=float(r.dep), rent=float(r.rent),
                 arch_year=None if pd.isna(r.arch) else float(r.arch), basement=bool(r.basement))
        res = compare(L, pool, as_of=r.date, conv_rate=conv_rate)
        rec = dict(gu=r.gu, dong=r.dong, usage=r.usage, area=L['area'], deposit=L['deposit'], actual=L['rent'],
                   date=r.date, status=res['status'], stage=res.get('stage'), n=res.get('n'))
        if res['status'] == 'ok':
            rec.update(median=res['median'], q25=res['q25'], q75=res['q75'], q10=res['q10'], q90=res['q90'],
                       percentile=res['percentile'], verdict=res['verdict'], grade=res['trust']['grade'],
                       fit=res['trust']['fit'], suff=res['trust']['sufficiency'])
            rec['err'] = abs(res['median'] - L['rent']) / L['rent']
        rows.append(rec)
    return pd.DataFrame(rows)


if __name__ == '__main__':
    import sys, glob
    files = sorted(glob.glob('data/rent_*_2025_2026.csv'))
    print('files:', files)
    raw = pd.concat([pd.read_csv(f, dtype=str) for f in files], ignore_index=True)
    rent, rep = clean(raw)
    print(rep)
    pool = Pool(rent)
    ex = dict(gu='관악구', dong='신림동', usage='단독다가구', area=18.0, deposit=1000, rent=50, arch_year=2015)
    print(compare(ex, pool))
