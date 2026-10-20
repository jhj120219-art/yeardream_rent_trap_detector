#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정제 + 비교 로직 검증표 생성 -> output/validation_report.xlsx, output/clean_rent_data.csv
실행: python run_validation.py   (data/rent_*_2025_2026.csv 를 전부 읽음)
"""
import glob, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / '_libs'))      # openpyxl (프로젝트 로컬 설치)
import numpy as np
import pandas as pd
import compare_rent as cr

HERE = Path(__file__).parent
OUT = HERE / 'output'; OUT.mkdir(exist_ok=True)
SEED = 7
PER_GU_BASES = 1500

# ------------------------------------------------------------ 1. 정제
files = sorted(glob.glob(str(HERE / 'data' / 'rent_*_2025_2026.csv')))
raw_by_gu = {}
for f in files:
    d = pd.read_csv(f, dtype=str)
    raw_by_gu[d['CGG_NM'].iloc[0]] = d
clean_tables, rent_parts = [], []
for gu, d in raw_by_gu.items():
    r, rep = cr.clean(d)
    rep = {'자치구': gu, **rep}
    clean_tables.append(rep); rent_parts.append(r)
rent = pd.concat(rent_parts, ignore_index=True)
clean_df = pd.DataFrame(clean_tables)
tot = clean_df.drop(columns='자치구').sum(numeric_only=True); tot['자치구'] = '합계'
clean_df = pd.concat([clean_df, pd.DataFrame([tot])], ignore_index=True)
rent.drop(columns=[c for c in rent.columns if c in ('LOTNO_SE', 'LOTNO_SE_NM')]).to_csv(
    OUT / 'clean_rent_data.csv', index=False, encoding='utf-8-sig')
print('정제 후', len(rent), '건,', rent.gu.nunique(), '개 구')

# ------------------------------------------------------------ 2. 시나리오 테스트(가상 데이터)
def mk(n, **kw):
    base = dict(gu='가구', dong='가동', usage='연립다세대', area=20.0, dep=1000.0, rent=50.0, arch=2015.0,
                basement=False, is_new=True, date=pd.Timestamp('2026-06-01'), dup_suspect=False)
    base.update(kw)
    rows = []
    for i in range(n):
        r = dict(base); r['rent'] = base['rent'] + (i % 5) - 2
        if isinstance(base['date'], pd.Timestamp):
            r['date'] = base['date'] + pd.Timedelta(days=i)
        rows.append(r)
    return pd.DataFrame(rows)

L0 = dict(gu='가구', dong='가동', usage='연립다세대', area=20.0, deposit=1000.0, rent=50.0, arch_year=2015.0)
AS_OF = '2026-09-01'
scen = []
def run(name, pool_df, listing=None, expect=None, as_of=AS_OF, note=''):
    res = cr.compare(listing or L0, cr.Pool(pool_df), as_of=as_of)
    got = res['stage'] if res['status'] == 'ok' else '보류'
    ok = (got == expect)
    scen.append({'시나리오': name, '기대 결과': expect, '실제 결과': got, '비교 건수': res.get('n'),
                 '통과': 'PASS' if ok else 'FAIL', '비고': note or res.get('message', '')})
    return res

run('1차: 유사 거래 15건 -> 1차에서 종료', mk(15), expect='1차')
run('2차 확대: 1차 3건 + 면적 +15% 7건', pd.concat([mk(3), mk(7, area=23.0)]), expect='2차')
run('3차 확대: 같은 동 3건 + 같은 구 다른 동 7건(면적 +22%)', pd.concat([mk(3), mk(7, dong='나동', area=24.0)]), expect='3차')
run('보류: 조건 완화해도 2건', mk(2), expect='보류')
run('지하/지상 분리: 지하 거래 20건만 있는 풀에서 지상 매물', mk(20, basement=True), expect='보류')
run('갱신 계약 제외: 갱신 20건만 있는 풀', mk(20, is_new=False), expect='보류')
run('미래 누수 방지: 기준일 이후 거래 20건', mk(20, date=pd.Timestamp('2026-10-01')), expect='보류')
run('보증금 범위: 보증금 5배 거래 15건', mk(15, dep=5000.0), expect='보류')
run('용도 분리: 오피스텔 20건 vs 연립다세대 매물', mk(20, usage='오피스텔'), expect='보류')
run('기간 제한: 30개월 전 거래 20건', mk(20, date=pd.Timestamp('2024-03-01')), expect='보류')
r_tr = cr.compare(L0, cr.Pool(pd.concat([mk(3), mk(7, dong='나동', area=24.0)])), as_of=AS_OF)
scen.append({'시나리오': '신뢰도: 3차(10건)에서는 "높음"이 나오면 안 됨', '기대 결과': '높음 아님', '실제 결과': r_tr['trust']['grade'],
             '비교 건수': r_tr['n'], '통과': 'PASS' if r_tr['trust']['grade'] != '높음' else 'FAIL', '비고': str(r_tr['trust'])})
scen_df = pd.DataFrame(scen)
print(scen_df[['시나리오', '기대 결과', '실제 결과', '통과']].to_string(index=False))

# ------------------------------------------------------------ 3. 백테스트
pool = cr.Pool(rent)
new = rent[rent['is_new']]
rng = np.random.default_rng(SEED)
base_parts = []
for gu, g in new.groupby('gu'):
    g = g[g['date'] >= g['date'].max() - pd.DateOffset(months=3)]
    base_parts.append(g.sample(min(PER_GU_BASES, len(g)), random_state=SEED))
bases = pd.concat(base_parts)
print('기준 매물', len(bases))
CONVS = [0.0, 0.04, 0.06]
bt = {c: cr.backtest(pool, bases, conv_rate=c) for c in CONVS}

def summ(df, by):
    rows = []
    for key, g in df.groupby(by):
        n = len(g); ok = g[g['status'] == 'ok']
        row = dict(zip(by if isinstance(by, list) else [by], key if isinstance(key, tuple) else (key,)))
        row['기준 매물'] = n
        for s in ['1차', '2차', '3차']:
            row[f'{s}(%)'] = round(100 * (ok['stage'] == s).sum() / n, 1)
        row['보류(%)'] = round(100 * (g['status'] != 'ok').sum() / n, 1)
        if len(ok):
            row['중앙 오차율(%)'] = round(100 * ok['err'].median(), 1)
            row['오차 ≤10%(%)'] = round(100 * (ok['err'] <= .10).mean(), 1)
            row['오차 ≤20%(%)'] = round(100 * (ok['err'] <= .20).mean(), 1)
            row['실제값 IQR 안(%) [기대 50]'] = round(100 * ((ok['actual'] >= ok['q25']) & (ok['actual'] <= ok['q75'])).mean(), 1)
            row['실제값 10~90% 안(%) [기대 80]'] = round(100 * ((ok['actual'] >= ok['q10']) & (ok['actual'] <= ok['q90'])).mean(), 1)
        rows.append(row)
    return pd.DataFrame(rows)

CONV_BEST = 0.0
conv_rows = []
for c, d in bt.items():
    ok = d[d['status'] == 'ok']
    conv_rows.append({'보증금 환산율(연)': c, '평가 건수': len(ok), '중앙 오차율(%)': round(100 * ok['err'].median(), 1),
                      '오차 ≤20%(%)': round(100 * (ok['err'] <= .2).mean(), 1),
                      '평균 오차율(%)': round(100 * ok['err'].mean(), 1)})
conv_df = pd.DataFrame(conv_rows)
CONV_BEST = float(conv_df.sort_values('중앙 오차율(%)').iloc[0]['보증금 환산율(연)'])
print(conv_df.to_string(index=False)); print('환산율 선택:', CONV_BEST)
d = bt[CONV_BEST].copy()
cr.CONV_RATE = CONV_BEST

tab_gu_usage = summ(d, ['gu', 'usage'])
tab_gu = summ(d, ['gu'])
tab_all = summ(d.assign(전체='전체'), ['전체'])
tab_stage = d[d['status'] == 'ok'].groupby('stage').agg(건수=('err', 'size'), 중앙오차=('err', 'median'),
          오차20이내=('err', lambda x: (x <= .2).mean()), 비교건수중앙값=('n', 'median')).reset_index()
tab_stage[['중앙오차', '오차20이내']] = (100 * tab_stage[['중앙오차', '오차20이내']]).round(1)

ok = d[d['status'] == 'ok'].copy()
tab_trust = ok.groupby('grade').agg(건수=('err', 'size'), 중앙오차=('err', 'median'), 평균오차=('err', 'mean'),
             오차20이내=('err', lambda x: (x <= .2).mean()),
             IQR안=('actual', lambda x: np.nan)).reset_index()
cover = ok.groupby('grade').apply(lambda g: ((g['actual'] >= g['q25']) & (g['actual'] <= g['q75'])).mean(), include_groups=False)
tab_trust['IQR안'] = tab_trust['grade'].map(cover)
for c in ['중앙오차', '평균오차', '오차20이내', 'IQR안']:
    tab_trust[c] = (100 * tab_trust[c]).round(1)
tab_trust['grade'] = pd.Categorical(tab_trust['grade'], ['높음', '보통', '낮음']); tab_trust = tab_trust.sort_values('grade')

# 판정 라벨이 실제 거래에서 얼마나 나오는가 (기대: 비싼 편 ≈10%, 다소 높음 ≈15%, 낮은 편 ≈25%)
lab = ok['verdict'].value_counts(normalize=True).mul(100).round(1).rename('비율(%)').reset_index()
lab.columns = ['판정', '비율(%)']
# 백분위 균일성(PIT): 10분위
pit = pd.cut(ok['percentile'], [-0.001, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0]).value_counts(normalize=True).sort_index().mul(100).round(1)
pit_df = pd.DataFrame({'백분위 구간': [str(i) for i in pit.index], '비율(%) [기대 10]': pit.values})

err_cases = ok.sort_values('err', ascending=False).head(40)[
    ['gu', 'dong', 'usage', 'area', 'deposit', 'actual', 'median', 'q25', 'q75', 'n', 'stage', 'grade', 'err']].copy()
err_cases['err'] = (100 * err_cases['err']).round(1)
err_cases.columns = ['구', '동', '용도', '면적㎡', '보증금', '실제월세', '비교중앙값', 'Q25', 'Q75', '비교건수', '단계', '신뢰도', '오차율(%)']

limits = pd.DataFrame({'항목': [
    '비교 기준', '데이터 범위', '평가 방법', '지하 여부', '건물 식별', '옵션·관리비', '시세 판정', '신뢰도 점수', '전환율', '중복'],
    '내용': [
    '신규 월세 계약만 사용, 같은 용도·같은 지하 여부, 계약일 이전 거래만(미래 데이터 누수 방지).',
    f'{", ".join(raw_by_gu)} 2025~2026 전월세 실거래. 나머지 구는 미검증.',
    f'각 구 최근 3개월 신규 월세 계약 최대 {PER_GU_BASES}건을 기준 매물로 가정하고 그 이전 거래로 예측한 월세 중앙값을 실제 월세와 비교.',
    '단독다가구는 층 값이 전부 0이라 반지하를 구분할 수 없음. 층<0 인 경우만 지하로 분리.',
    '건물명이 대부분 비어 있고 호수가 없어 같은 건물을 식별할 수 없음.',
    '인터넷·엘리베이터·관리비·옵션은 실거래 데이터에 없음. 오차의 일부는 이 차이에서 올 수 있으나 분리 못 함.',
    '월세가 비교 분포의 Q75·Q90보다 높을 때 "다소 높음/비싼 편"으로 표시하고, 신뢰도 낮음이면 판정하지 않음. "사기" 판정이 아님.',
    '비교 적합도(단계·지하/건축연도 정보)와 데이터 충분도(건수·최근성·분포 폭)를 합친 규칙 기반 점수. 통계적 신뢰확률이 아님.',
    f'보증금 차이를 월세로 환산하는 연 전환율은 백테스트에서 오차가 가장 낮은 값({CONV_BEST})을 사용.',
    '동일 행이 많지만 호수가 없어 실제 중복과 구분 불가 -> 삭제하지 않고 dup_suspect 플래그만 부여.']})

# ------------------------------------------------------------ 4. 엑셀 저장
xl = OUT / 'validation_report.xlsx'
with pd.ExcelWriter(xl, engine='openpyxl') as w:
    clean_df.to_excel(w, sheet_name='1_정제결과표', index=False)
    scen_df.to_excel(w, sheet_name='2_탐색로직_시나리오', index=False)
    tab_all.to_excel(w, sheet_name='3_시세비교_전체', index=False)
    tab_gu.to_excel(w, sheet_name='3_시세비교_구별', index=False)
    tab_gu_usage.to_excel(w, sheet_name='3_시세비교_구x용도', index=False)
    tab_stage.to_excel(w, sheet_name='3_단계별_오차', index=False)
    tab_trust.to_excel(w, sheet_name='4_신뢰도등급_보정', index=False)
    lab.to_excel(w, sheet_name='4_판정라벨_비율', index=False)
    pit_df.to_excel(w, sheet_name='4_백분위_분포', index=False)
    conv_df.to_excel(w, sheet_name='5_보증금환산_비교', index=False)
    err_cases.to_excel(w, sheet_name='6_오차큰_사례', index=False)
    limits.to_excel(w, sheet_name='7_가정과_한계', index=False)
    from openpyxl.styles import Font, PatternFill
    for ws in w.book.worksheets:
        for c in ws[1]:
            c.font = Font(bold=True); c.fill = PatternFill('solid', fgColor='DDEBF7')
        for col in ws.columns:
            width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
            ws.column_dimensions[col[0].column_letter].width = min(max(10, width * 1.3 + 2), 70)
        ws.freeze_panes = 'A2'
d.to_csv(OUT / 'backtest_all.csv', index=False, encoding='utf-8-sig')
print('\n=== 전체 ==='); print(tab_all.to_string(index=False))
print('\n=== 구별 ==='); print(tab_gu.to_string(index=False))
print('\n=== 구x용도 ==='); print(tab_gu_usage.to_string(index=False))
print('\n=== 단계별 ==='); print(tab_stage.to_string(index=False))
print('\n=== 신뢰도 등급 ==='); print(tab_trust.to_string(index=False))
print('\n=== 판정 라벨 비율 ==='); print(lab.to_string(index=False))
print('\n=== 백분위 분포 ==='); print(pit_df.to_string(index=False))
print('saved', xl)
