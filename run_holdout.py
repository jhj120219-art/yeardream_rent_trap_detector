#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""홀드아웃 검증: 설계·튜닝에 한 번도 쓰지 않은 서대문구(11410)·성북구(11290) 2025~2026 데이터로 '고정된 규칙'을 평가한다.

[규칙 고정] compare_rent.STAGES, MIN_N, 신뢰도 점수, CONV_RATE=0, analyze.POLICY 는 이 스크립트에서 수정하지 않는다.
[기준 매물] 설계 때와 같은 방식: 구별 최근 3개월 신규 월세 계약 최대 1,500건(seed 7), 계약일 이전 거래만 사용.

[통과 기준 — 결과를 보기 전에 정함, 사후 조정 금지]
  C1 신뢰도 등급 단조성: 중앙 오차 높음 < 보통 < 낮음
  C2 높음 등급: 중앙 오차 ≤ 15.0%, 오차 20% 이내 비율 ≥ 60%
  C3 전체 중앙 오차 ≤ 19.7%  (설계 16.7% + 3.0%p)
  C4 실제값이 사분위 범위(Q25~Q75) 안에 들어오는 비율 45~55%
  C5 비교 거래 부족으로 판단 보류한 비율 ≤ 2%
  C6 안전 규칙 위반 0건(analyze_listing 불변식: 단독다가구 UPPER_TAIL 금지, 단독다가구 COMPARED는 확인된 지상층·신뢰도 높음·1~2차뿐,
     3차·REFERENCE_ONLY에는 UPPER/LOWER 라벨 없음, UPPER_TAIL은 신뢰도 높음뿐, 사용자 문구 금지어 없음)
  C7 "비싼 편(UPPER_TAIL)" 라벨 비율이 8~16%  (설계 12.0%)
이 중 하나라도 실패하면 결과를 그대로 기록하고, 규칙을 고친 경우 이 자료는 더 이상 독립 평가용이 아니라 '탐색적 검증'으로 표시한다.
실행: python run_holdout.py   -> output/holdout_results.csv, output/holdout_summary.json
"""
import glob, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import analyze as an
import compare_rent as cr

HERE = Path(__file__).parent
OUT = HERE / 'output'
HOLD_GU = {'11410': '서대문구', '11290': '성북구'}
SEED, PER_GU = 7, 1500

# ------------------------------------------------------------ 데이터·풀
parts = []
for f in sorted(glob.glob(str(HERE / 'data' / 'holdout' / 'rent_*_2025_2026.csv'))):
    r, rep = cr.clean(pd.read_csv(f, dtype=str))
    parts.append(r)
    print(Path(f).name, '정제 후 월세', rep['정제 후 월세'], '신규', rep['  정제 후 신규(비교 풀)'])
rent = pd.concat(parts, ignore_index=True)
assert set(rent['gu']) == set(HOLD_GU.values()), set(rent['gu'])
pool = cr.Pool(rent)
pool.dong_by_code = (rent.assign(code=rent['CGG_CD'].str.zfill(5) + rent['STDG_CD'].str.zfill(5)).drop_duplicates('code')
                     .set_index('code')['dong'].to_dict())
pool.dongs = {(g, d) for g, d in zip(rent['gu'], rent['dong'])}
pool.renewals_excluded_by_gu = {g: int((rent['gu'] == g).sum() - ((rent['gu'] == g) & rent['is_new']).sum()) for g in rent['gu'].unique()}
new = rent[rent['is_new']]
bases = pd.concat([g[g['date'] >= g['date'].max() - pd.DateOffset(months=3)].sample(min(PER_GU, len(g)), random_state=SEED)
                   for _, g in new.groupby('gu')])
print('기준 매물', len(bases))

# ------------------------------------------------------------ 백테스트(고정 규칙)
bt = cr.backtest(pool, bases, conv_rate=0.0)
ok = bt[bt['status'] == 'ok'].copy()


def summarize(df, label):
    n = len(df)
    o = df[df['status'] == 'ok']
    iqr = ((o['actual'] >= o['q25']) & (o['actual'] <= o['q75'])).mean()
    return {'구분': label, '기준 매물': n, '보류(%)': round(100 * (df['status'] != 'ok').mean(), 2),
            '1차(%)': round(100 * (o['stage'] == '1차').sum() / n, 1), '2차(%)': round(100 * (o['stage'] == '2차').sum() / n, 1),
            '3차(%)': round(100 * (o['stage'] == '3차').sum() / n, 1),
            '중앙 오차(%)': round(100 * o['err'].median(), 1), '오차 ≤20%(%)': round(100 * (o['err'] <= .2).mean(), 1),
            'IQR 안(%)': round(100 * iqr, 1), '비싼 편 라벨(%)': round(100 * (o['verdict'] == '비싼 편(상위 10%)').mean(), 1)}


design = pd.read_csv(OUT / 'backtest_all.csv')
rows = [summarize(design, '설계(6개 구)'), summarize(bt, '홀드아웃(서대문·성북)')]
for g in sorted(bt['gu'].unique()):
    rows.append(summarize(bt[bt['gu'] == g], '홀드아웃 ' + g))
for u in cr.USAGES:
    rows.append(summarize(bt[bt['usage'] == u], '홀드아웃 ' + u))
tab = pd.DataFrame(rows)
print(tab.to_string(index=False))

grade = ok.groupby('grade').agg(건수=('err', 'size'), 중앙오차=('err', 'median'), 오차20이내=('err', lambda x: (x <= .2).mean())).reindex(['높음', '보통', '낮음'])
grade_design = design[design['status'] == 'ok'].groupby('grade').agg(중앙오차=('err', 'median'), 오차20이내=('err', lambda x: (x <= .2).mean())).reindex(['높음', '보통', '낮음'])
print('\n신뢰도 등급(홀드아웃):'); print((grade * [1, 100, 100]).round(1).to_string())
print('신뢰도 등급(설계):'); print((grade_design * 100).round(1).to_string())
stage = ok.groupby('stage').agg(건수=('err', 'size'), 중앙오차=('err', 'median')).assign(중앙오차=lambda d: (100 * d['중앙오차']).round(1))
print('\n단계별:'); print(stage.to_string())

# ------------------------------------------------------------ 안전 규칙 불변식(analyze_listing)
an.SUPPORTED_GU.update(HOLD_GU)
an.GU_BY_NAME.update({v: k for k, v in HOLD_GU.items()})
TYPE_EN = {'아파트': 'APARTMENT', '연립다세대': 'MULTI_UNIT', '단독다가구': 'DETACHED_MULTI', '오피스텔': 'OFFICETEL'}
FORBIDDEN = ('함정', '사기', '불법', '바가지')
rng = np.random.default_rng(SEED)
sample = bases.sample(min(1500, len(bases)), random_state=SEED)
viol, counts, n_calls = [], {'COMPARED': 0, 'REFERENCE_ONLY': 0, 'INSUFFICIENT_DATA': 0, 'OTHER': 0}, 0
per_listing = []   # (용도, 층 확인 가정 COMPARED, 층 미확인 COMPARED)
labels = {}
for r in sample.itertuples():
    base = dict(district_code=str(r.CGG_CD).zfill(5), legal_dong_code=str(r.CGG_CD).zfill(5) + str(r.STDG_CD).zfill(5),
                building_type=TYPE_EN[r.usage], area_m2=float(r.area), deposit_10k_krw=float(r.dep), rent_10k_krw=float(r.rent),
                built_year=None if pd.isna(r.arch) else float(r.arch), as_of=str(pd.Timestamp(r.date).date()))
    variants = []
    if r.usage == '단독다가구':
        variants = [dict(base, area_basis='CONTRACT', floor_type='GROUND', floor_source='USER_CONFIRMED', floor=2),
                    dict(base, area_basis='CONTRACT', floor_type='BASEMENT', floor_source='USER_CONFIRMED'),
                    dict(base, area_basis='CONTRACT')]
    else:
        fl = -1 if r.basement else 3
        variants = [dict(base, area_basis='EXCLUSIVE', floor=fl)]
    main_c, unk_c = None, None
    for vi, p in enumerate(variants):
        res = an.analyze_listing(p, pool)
        if vi == 0: main_c = (res['status'] == 'COMPARED')
        if (r.usage == '단독다가구' and vi == 2) or (r.usage != '단독다가구' and vi == 0): unk_c = (res['status'] == 'COMPARED')
        n_calls += 1
        st, lab, grd = res['status'], res['price_label'], res['confidence_grade']
        counts[st if st in counts else 'OTHER'] += 1
        labels[lab] = labels.get(lab, 0) + 1
        det = r.usage == '단독다가구'
        if st not in an.ENUM_STATUS or lab not in an.ENUM_LABEL:
            viol.append(('ENUM', st, lab))
        if det and lab == 'UPPER_TAIL':
            viol.append(('DETACHED_UPPER_TAIL', st, lab))
        if det and st == 'COMPARED' and not (p.get('floor_type') == 'GROUND' and grd == 'HIGH' and res['stage'] in (1, 2)):
            viol.append(('DETACHED_COMPARED_CONDITION', st, grd, res['stage'], p.get('floor_type')))
        if st != 'COMPARED' and lab != 'UNRATED':
            viol.append(('LABEL_WITHOUT_COMPARED', st, lab))
        if res.get('stage') == 3 and st == 'COMPARED':
            viol.append(('STAGE3_COMPARED',))
        if lab == 'UPPER_TAIL' and grd != 'HIGH':
            viol.append(('UPPER_TAIL_NOT_HIGH', grd))
        txt = ' '.join(res.get('messages', []) + list(res.get('warning_texts', {}).values()))
        if any(w in txt for w in FORBIDDEN):
            viol.append(('FORBIDDEN_WORD',))
        if st == 'COMPARED' and r.usage == '단독다가구' and p.get('floor_type') != 'GROUND':
            viol.append(('DETACHED_COMPARED_WITHOUT_GROUND',))
    per_listing.append((r.usage, bool(main_c), bool(unk_c)))
per_df = pd.DataFrame(per_listing, columns=['usage', 'floors_confirmed', 'floor_unknown'])
print('\n판정 가능(COMPARED) 비율, 매물 단위(층 확인 가정 / 층 미확인): %.1f%% / %.1f%%' % (100 * per_df['floors_confirmed'].mean(), 100 * per_df['floor_unknown'].mean()))
print(per_df.groupby('usage')[['floors_confirmed', 'floor_unknown']].mean().mul(100).round(1).to_string())
print('\n불변식 검사: 호출', n_calls, '| 상태 분포', counts, '| 위반', len(viol), viol[:5])
cmp_share = counts['COMPARED'] / n_calls
tail_rate = ok['verdict'].eq('비싼 편(상위 10%)').mean()

# ------------------------------------------------------------ 통과 기준 판정
o_h = ok[ok['grade'] == '높음']
mono = grade.loc['높음', '중앙오차'] < grade.loc['보통', '중앙오차'] < grade.loc['낮음', '중앙오차']
iqr = ((ok['actual'] >= ok['q25']) & (ok['actual'] <= ok['q75'])).mean()
crit = [
    ('C1 등급 단조성(높음<보통<낮음)', mono, f"{grade['중앙오차'].round(3).to_dict()}"),
    ('C2 높음 등급 중앙오차≤15.0% 그리고 20%이내≥60%', (o_h['err'].median() <= 0.15) and ((o_h['err'] <= 0.2).mean() >= 0.60),
     f"{100*o_h['err'].median():.1f}% / {100*(o_h['err'] <= 0.2).mean():.1f}%"),
    ('C3 전체 중앙오차≤19.7%', ok['err'].median() <= 0.197, f"{100*ok['err'].median():.1f}%"),
    ('C4 IQR 포함 45~55%', 0.45 <= iqr <= 0.55, f"{100*iqr:.1f}%"),
    ('C5 보류≤2%', (bt['status'] != 'ok').mean() <= 0.02, f"{100*(bt['status'] != 'ok').mean():.2f}%"),
    ('C6 안전 규칙 위반 0건', len(viol) == 0, f'{len(viol)}건'),
    ('C7 비싼 편 라벨 8~16%', 0.08 <= tail_rate <= 0.16, f'{100*tail_rate:.1f}%'),
]
print('\n=== 통과 기준 판정 ===')
for name, passed, detail in crit:
    print(('PASS ' if passed else 'FAIL ') + name + ' -> ' + detail)
summary = {'기준 매물': int(len(bt)), '통과': int(sum(c[1] for c in crit)), '기준 수': len(crit),
           '판정': [{'기준': n, '결과': 'PASS' if p else 'FAIL', '값': d} for n, p, d in crit],
           '안전 규칙 위반': viol[:20], 'analyze 호출 수': n_calls, '상태 분포': counts,
           '판정 가능 비율_층확인 가정(%)': round(100 * per_df['floors_confirmed'].mean(), 1), '판정 가능 비율_층 미확인(%)': round(100 * per_df['floor_unknown'].mean(), 1), '라벨 분포': labels}
tab.to_csv(OUT / 'holdout_results.csv', index=False, encoding='utf-8-sig')
(OUT / 'holdout_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
bt.drop(columns=['date']).to_csv(OUT / 'holdout_backtest_cases.csv', index=False, encoding='utf-8-sig')
print('\n통과', summary['통과'], '/', summary['기준 수'])
