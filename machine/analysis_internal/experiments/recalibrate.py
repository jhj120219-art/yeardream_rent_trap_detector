# -*- coding: utf-8 -*-
"""신뢰도 확률 재보정 실험 — 설계 run 의 구 단위 교차검증 예측(p20)을 입력으로, 구를 바꿔 가며 등온(isotonic)/Platt 보정을 학습·적용한다(중첩 검증).
채택 기준: Brier 개선 + 보정 곡선 개선 + 등급 컷오프를 바꿔도 등급 순서/적중률이 유지. 아니면 기각(현재 로지스틱 그대로 사용).
실행: python recalibrate.py [results/<run_id>]  (기본: 가장 최근 design6 run)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import INTERNAL, np, pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

runs = sorted((INTERNAL / 'results').glob('*_design6'))
run = Path(sys.argv[1]) if len(sys.argv) > 1 else runs[-1]
V = pd.read_csv(run / 'records.csv')
y = (V['err'] <= .2).astype(int).values
p = V['p20'].values
print('run', run.name, '| n', len(V))


def calib_table(pp, label):
    print(f'  [{label}] Brier {brier_score_loss(y, pp):.4f} | AUC {roc_auc_score(y, pp):.3f}')
    for lo, hi in ((0, .3), (.3, .5), (.5, .6), (.6, .7), (.7, .8), (.8, .9), (.9, 1.01)):
        m = (pp >= lo) & (pp < hi)
        if m.sum():
            print(f'     {lo:.1f}-{min(hi,1):.1f}: n={int(m.sum()):4d} 예측 {100*pp[m].mean():5.1f}% / 실제 {100*y[m].mean():5.1f}%')


calib_table(p, '현재(LOO 로지스틱)')
iso = np.zeros(len(V)); platt = np.zeros(len(V))
for g in V['gu'].unique():
    te = (V['gu'] == g).values
    ir = IsotonicRegression(out_of_bounds='clip', y_min=0.02, y_max=0.98).fit(p[~te], y[~te])
    iso[te] = ir.predict(p[te])
    lr = LogisticRegression().fit(np.log(p[~te] / (1 - p[~te])).reshape(-1, 1), y[~te])
    platt[te] = lr.predict_proba(np.log(p[te] / (1 - p[te])).reshape(-1, 1))[:, 1]
print('\n=== 중첩 구 교차검증 후 보정 ===')
calib_table(iso, '등온 보정')
calib_table(platt, 'Platt 보정')

print('\n=== 등급(0.75/0.55) 비교 ===')
for name, pp in (('현재', p), ('등온', iso), ('Platt', platt)):
    g = np.where(pp >= .75, '높음', np.where(pp >= .55, '보통', '낮음'))
    s = []
    for lab in ('높음', '보통', '낮음'):
        m = g == lab
        s.append(f'{lab} {100*m.mean():.0f}% -> {100*y[m].mean():.1f}%')
    print(f'  {name}: ' + ' | '.join(s))
