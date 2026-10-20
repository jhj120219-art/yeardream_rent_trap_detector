#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서울시 전월세가(RENT_AREA)와 국토부 실거래가 공개시스템 CSV(전용면적)를 건별로 대조해 면적 기준을 확인.
입력: data/molit_downloads/*.csv (국토부 '조건별 자료제공' CSV, cp949, 머리글 15줄) + output/clean_rent_data.csv
실행: python check_area_basis.py
매칭 키: 자치구·동·본번·부번·계약일·보증금·월세·층·건축년도. 양쪽에서 키가 정확히 1건씩일 때만 '확정 일치'로 본다.
"""
import glob, re, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DL = HERE / 'data' / 'molit_downloads'
USAGE_FROM_NAME = {'오피스텔': '오피스텔', '연립다세대': '연립다세대', '단독다가구': '단독다가구', '아파트': '아파트'}


def read_molit(path):
    raw = Path(path).read_bytes().decode('cp949')
    lines = raw.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith('"NO"'))
    gu = re.search(r'시군구 : ([^\s"]+)', raw).group(1)
    kind = re.search(r'실거래구분 : ([^\r\n"]+)', raw).group(1)
    df = pd.read_csv(path, encoding='cp949', skiprows=start, thousands=',', dtype=str)
    df = df.rename(columns={'전용면적(㎡)': 'excl', '계약면적(㎡)': 'excl', '보증금(만원)': 'dep', '월세금(만원)': 'rent', '계약구분': 'new_flag',
                            '계약년월': 'ym', '계약일': 'day', '층': 'flr', '건축년도': 'arch', '본번': 'bon', '부번': 'bu'})
    if '전월세구분' in df.columns:
        df = df[df['전월세구분'] == '월세']
    dong = df['시군구'].str.split().str[-1]
    has_bon = 'bon' in df.columns
    out = pd.DataFrame({
        'gu': gu, 'dong': dong,
        'bon': df['bon'].astype(str).str.zfill(4) if has_bon else '', 'bu': df['bu'].astype(str).str.zfill(4) if has_bon else '',
        'prd': df['계약기간'].astype(str),
        'date': pd.to_datetime(df['ym'].astype(str) + df['day'].astype(str).str.zfill(2), format='%Y%m%d', errors='coerce'),
        'dep': pd.to_numeric(df['dep'].str.replace(',', ''), errors='coerce'),
        'rent': pd.to_numeric(df['rent'].str.replace(',', ''), errors='coerce'),
        'flr': pd.to_numeric(df['flr'], errors='coerce') if 'flr' in df.columns else np.nan,
        'arch': pd.to_numeric(df['arch'], errors='coerce'),
        'excl': pd.to_numeric(df['excl'], errors='coerce'), 'new_flag': df['new_flag']})
    out['kind'] = kind
    return out


seoul = pd.read_csv(HERE / 'output' / 'clean_rent_data.csv', parse_dates=['date'], low_memory=False,
                    dtype={'MNO': str, 'SNO': str})
seoul['bon'] = seoul['MNO'].astype(str).str.zfill(4); seoul['bu'] = seoul['SNO'].astype(str).str.zfill(4)


def _prd(s):                                   # '26.11~28.11' -> '202611~202811'
    m = re.match(r'(\d{2})\.(\d{2})~(\d{2})\.(\d{2})', str(s))
    return f'20{m[1]}{m[2]}~20{m[3]}{m[4]}' if m else ''


seoul['prd'] = seoul['CTRT_PRD'].map(_prd)
# 서울시 데이터의 층(flr)은 단독다가구는 전부 0, 건축연도는 ARCH_YR -> arch
KEY = ['gu', 'dong', 'bon', 'bu', 'date', 'dep', 'rent', 'flr', 'arch']

report = []
for f in sorted(glob.glob(str(DL / '*.csv'))):
    m = read_molit(f)
    kind = m['kind'].iloc[0]
    usage = next(v for k, v in USAGE_FROM_NAME.items() if k in kind.replace('/', ''))
    gu = m['gu'].iloc[0]
    s = seoul[(seoul['gu'] == gu) & (seoul['usage'] == usage)].copy()
    # 단독다가구는 서울시 층이 전부 0 -> 층을 키에서 제외
    key = KEY if usage != '단독다가구' else ['gu', 'dong', 'date', 'dep', 'rent', 'prd']   # 단독다가구는 번지 마스킹·층 없음
    # 서울시 쪽 층은 float, 국토부는 정수/빈값. 비교 가능하게 반올림
    for d in (m, s):
        d['dep'] = d['dep'].round(0); d['rent'] = d['rent'].round(0)
        if 'flr' in d.columns: d['flr'] = d['flr'].round(0)
    m_ = m.dropna(subset=['date', 'dep', 'rent']).copy(); s_ = s.dropna(subset=['date', 'dep', 'rent']).copy()
    m_['kk'] = m_.groupby(key).cumcount(); s_['kk'] = s_.groupby(key).cumcount()
    mc = m_.groupby(key).size().rename('n_m'); sc = s_.groupby(key).size().rename('n_s')
    both = pd.concat([mc, sc], axis=1, join='inner')
    uniq = both[(both.n_m == 1) & (both.n_s == 1)].index
    mm = m_.set_index(key).loc[uniq, ['excl']]; ss = s_.set_index(key).loc[uniq, ['area']].rename(columns={'area': 'rent_area'})
    j = mm.join(ss)
    j['diff'] = j['rent_area'] - j['excl']
    j['absdiff'] = j['diff'].abs()
    nm, ns = len(m_), len(s_)
    basis = '계약면적' if usage == '단독다가구' else '전용면적'
    row = dict(유형=usage, 구=gu, 국토부_면적명=basis, 국토부_월세=nm, 서울시_월세=ns,
               키가_양쪽에_있는_고유_일치=len(j),
               일치율_국토부기준=round(100 * len(j) / nm, 1) if nm else None)
    if len(j):
        row.update({'면적 동일(|차|≤0.01㎡) %': round(100 * (j.absdiff <= 0.01).mean(), 1),
                    '|차|≤0.1㎡ %': round(100 * (j.absdiff <= 0.1).mean(), 1),
                    '|차|≤0.5㎡ %': round(100 * (j.absdiff <= 0.5).mean(), 1),
                    '|차|>1㎡ %': round(100 * (j.absdiff > 1).mean(), 1),
                    '중앙 차이(㎡)': round(float(j['diff'].median()), 3),
                    '평균 비율(서울시/국토부)': round(float((j['rent_area'] / j['excl']).mean()), 4),
                    '서울시가 더 큼 %': round(100 * (j['diff'] > 0.01).mean(), 1),
                    '서울시가 더 작음 %': round(100 * (j['diff'] < -0.01).mean(), 1)})
    report.append(row)
    j.reset_index().to_csv(HERE / 'output' / f'area_check_{usage}_{gu}.csv', index=False, encoding='utf-8-sig')
    # 서울시 값이 반올림되어 있는지(소수 자릿수)
    dec_s = s['area'].map(lambda x: len(str(x).split('.')[-1]) if '.' in str(x) else 0)
    dec_m = m['excl'].map(lambda x: len(str(x).split('.')[-1].rstrip('0')) if '.' in str(x) else 0)
    row['서울시 면적 소수자리 평균'] = round(float(dec_s.mean()), 2); row['국토부 면적 소수자리 평균'] = round(float(dec_m.mean()), 2)
    print(f'\n== {usage} / {gu}: 국토부 월세 {nm}, 서울시 월세 {ns}')
    for k, v in row.items():
        if k not in ('유형', '구'): print(f'  {k}: {v}')

pd.DataFrame(report).to_csv(HERE / 'output' / 'area_basis_check_summary.csv', index=False, encoding='utf-8-sig')
