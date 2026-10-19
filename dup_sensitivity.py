#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""중복 의심 행 처리에 대한 민감도 분석.
A안: 비교 풀 그대로(중복 의심 행 유지)  B안: 비교 풀에서 동일 조건 행을 1건으로 통합
백테스트 대상(기준 매물 8,995건)은 두 안에서 완전히 동일. 통합은 '비교 풀'에만 적용.
실행: python dup_sensitivity.py   (먼저 run_validation.py 로 output/clean_rent_data.csv 생성)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / '_libs'))
import numpy as np
import pandas as pd
import compare_rent as cr

HERE = Path(__file__).parent
rent = pd.read_csv(HERE / 'output' / 'clean_rent_data.csv', parse_dates=['date'], low_memory=False)
for c in ('is_new', 'basement', 'dup_suspect'):
    rent[c] = rent[c].astype(bool)

# 기준 매물: run_validation.py 와 동일한 방식/시드 (구별 최근 3개월 신규 월세, 최대 1,500건)
new = rent[rent['is_new']]
parts = []
for gu, g in new.groupby('gu'):
    g = g[g['date'] >= g['date'].max() - pd.DateOffset(months=3)]
    parts.append(g.sample(min(1500, len(g)), random_state=7))
bases = pd.concat(parts)

KEYS = ['gu', 'dong', 'usage', 'MNO', 'SNO', 'flr', 'CTRT_DAY', 'area', 'dep', 'rent', 'NEW_UPDT_YN']
dedup = rent.drop_duplicates(subset=KEYS, keep='first')
print('비교 풀 행 수  A안:', len(rent), ' B안:', len(dedup), ' 통합된 행:', len(rent) - len(dedup),
      f'({100 * (len(rent) - len(dedup)) / len(rent):.1f}%)')

rA = cr.backtest(cr.Pool(rent), bases, conv_rate=0.0)
rB = cr.backtest(cr.Pool(dedup), bases, conv_rate=0.0)


def summary(r, label):
    ok = r[r['status'] == 'ok']
    return {'안': label, '평가 건수': len(ok), '보류(%)': round(100 * (r['status'] != 'ok').mean(), 2),
            '1차(%)': round(100 * (ok['stage'] == '1차').sum() / len(r), 1),
            '2차(%)': round(100 * (ok['stage'] == '2차').sum() / len(r), 1),
            '3차(%)': round(100 * (ok['stage'] == '3차').sum() / len(r), 1),
            '중앙 오차(%)': round(100 * ok['err'].median(), 2), '오차 ≤20%(%)': round(100 * (ok['err'] <= .2).mean(), 2),
            'IQR 안(%)': round(100 * ((ok['actual'] >= ok['q25']) & (ok['actual'] <= ok['q75'])).mean(), 2),
            '높음(%)': round(100 * (ok['grade'] == '높음').mean(), 1), '보통(%)': round(100 * (ok['grade'] == '보통').mean(), 1),
            '낮음(%)': round(100 * (ok['grade'] == '낮음').mean(), 1),
            '높음 중앙오차(%)': round(100 * ok[ok['grade'] == '높음']['err'].median(), 2),
            '보통 중앙오차(%)': round(100 * ok[ok['grade'] == '보통']['err'].median(), 2),
            '낮음 중앙오차(%)': round(100 * ok[ok['grade'] == '낮음']['err'].median(), 2),
            '비싼 편(%)': round(100 * (ok['verdict'] == '비싼 편(상위 10%)').mean(), 1),
            '다소 높음(%)': round(100 * (ok['verdict'] == '다소 높음(상위 25%)').mean(), 1),
            '참고만(%)': round(100 * (ok['verdict'] == '참고만(신뢰도 낮음)').mean(), 1)}


tab = pd.DataFrame([summary(rA, 'A 그대로'), summary(rB, 'B 통합')]).set_index('안').T
print(tab.to_string())
by = []
for u in cr.USAGES:
    for lab, r in (('A', rA), ('B', rB)):
        g = r[(r['usage'] == u) & (r['status'] == 'ok')]
        by.append({'용도': u, '안': lab, '건수': len(g), '중앙 오차(%)': round(100 * g['err'].median(), 2),
                   '오차 ≤20%(%)': round(100 * (g['err'] <= .2).mean(), 2),
                   '1차(%)': round(100 * (g['stage'] == '1차').mean(), 1), '높음(%)': round(100 * (g['grade'] == '높음').mean(), 1)})
by = pd.DataFrame(by)
print(by.to_string(index=False))

# 판정이 달라진 매물
m = pd.DataFrame({'gu': rA['gu'], 'usage': rA['usage'], 'actual': rA['actual'], 'a_verdict': rA['verdict'], 'b_verdict': rB['verdict'],
                  'a_grade': rA['grade'], 'b_grade': rB['grade'], 'a_stage': rA['stage'], 'b_stage': rB['stage'],
                  'a_med': rA['median'], 'b_med': rB['median'], 'a_n': rA['n'], 'b_n': rB['n']})
both = m[m['a_verdict'].notna() & m['b_verdict'].notna()]
chg_verdict = (both['a_verdict'] != both['b_verdict']).mean()
chg_grade = (both['a_grade'] != both['b_grade']).mean()
chg_stage = (both['a_stage'] != both['b_stage']).mean()
shift = ((both['b_med'] - both['a_med']).abs() / both['a_med'])
print(f"\nA↔B 판정 라벨이 달라진 매물: {100*chg_verdict:.1f}% ({int((both['a_verdict']!=both['b_verdict']).sum())}건 / {len(both)})")
print(f"신뢰도 등급이 달라진 매물: {100*chg_grade:.1f}%   탐색 단계가 달라진 매물: {100*chg_stage:.1f}%")
print(f"비교 중앙값 이동(상대): 중앙값 {100*shift.median():.2f}%, 90% 분위 {100*shift.quantile(.9):.2f}%, 최대 {100*shift.max():.1f}%")
strong = both[(both['a_verdict'].isin(['비싼 편(상위 10%)']) != both['b_verdict'].isin(['비싼 편(상위 10%)']))]
print(f"'비싼 편' 여부가 바뀐 매물: {len(strong)}건 ({100*len(strong)/len(both):.2f}%)")
print('판정 변경 상위 조합:'); print(both[both['a_verdict'] != both['b_verdict']].groupby(['a_verdict', 'b_verdict']).size().sort_values(ascending=False).head(6).to_string())
out = HERE / 'output'
tab.to_csv(out / 'dup_sensitivity_summary.csv', encoding='utf-8-sig')
by.to_csv(out / 'dup_sensitivity_by_usage.csv', index=False, encoding='utf-8-sig')
m.to_csv(out / 'dup_sensitivity_cases.csv', index=False, encoding='utf-8-sig')
