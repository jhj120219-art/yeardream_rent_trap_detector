# -*- coding: utf-8 -*-
"""입력 오류 주입 민감도 실험 — 설계 6개 구 기준 매물(8,995건)에서만. 홀드아웃(송파·강북) 미사용.
정확한 입력으로 낸 결과(기준)와, 필드를 일부러 틀리게 바꾼 입력의 결과를 비교한다.
 - 라벨 유지 / 다른 라벨로 바뀜(조용한 오판) / 보류(UNRATED)로 바뀜(안전한 차단) / 보류였던 것이 판정됨
 - 기본 입력 검증 규칙(범위·시세 이탈)이 오류를 잡아내는 비율
 - 지번 오류는 0단계 오진입(다른 건물과 비교) 여부
실행: python input_errors.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import ROOT, INTERNAL, np, pd, load_policy, load_rent, load_building_cache, make_bases
from engine_v2 import EngineV2

policy = load_policy()
rent = load_rent(ROOT / 'output' / 'clean_rent_data.csv')
cache = load_building_cache(ROOT / policy['stage0']['building_cache'])
ev = policy['evaluation']
bases = make_bases(rent, ev['seed'], ev['bases_per_gu'], ev['recent_months'])
eng = EngineV2(rent, cache, policy)
rng = np.random.default_rng(3)

# 지번 오매칭용: 같은 동의 다른 단일 건물 지번
by_dong = {}
for key in eng.lots:
    c, s, m, n = key.split('|')
    if cache.get((c, s, m, n)) == 1:
        by_dong.setdefault((c, s), []).append((m, n))


def judge(r):
    rec = eng.evaluate(r)
    if rec['source'] == 'NONE':
        return dict(rec=rec, grade='낮음', label='UNRATED', reason='NO_COMPARABLES', p=np.nan)
    p = eng.trust_prob(rec)
    g = eng.grade(p)
    lb, why = eng.label(r['rent'], rec, g)
    return dict(rec=rec, grade=g, label=lb, reason=why, p=p)


def sanity_flag(r, out):
    """입력 검증 규칙(후보): 값 범위, 시세 이탈. 입력값과 그 입력으로 얻은 비교군만 사용한다."""
    if not (3 <= r['rent'] <= 500) or not (5 <= r['area'] <= 200) or r['dep'] < 0:
        return True
    rec = out['rec']
    if rec['source'] != 'NONE':
        ratio = r['rent'] / rec['pred']
        if ratio > 2.5 or ratio < 0.4:
            return True
    return False


def mk(**kw):
    def f(r):
        r = dict(r)
        for k, fn in kw.items():
            r[k] = fn(r)
        return r
    return f


def lot_mismatch(r):
    if r['usage'] == '단독다가구':
        return None
    cand = [t for t in by_dong.get((r['CGG_CD'], r['STDG_CD']), []) if t != (r['MNO'], r['SNO'])]
    if not cand:
        return None
    r = dict(r)
    r['MNO'], r['SNO'] = cand[int(rng.integers(len(cand)))]
    return r


def lot_drop(r):
    r = dict(r)
    r['MNO'] = np.nan
    r['SNO'] = np.nan
    return r


def usage_swap(r):
    sw = {'연립다세대': '단독다가구', '단독다가구': '연립다세대', '오피스텔': '아파트', '아파트': '오피스텔'}
    r = dict(r)
    r['usage'] = sw[r['usage']]
    return r


SCEN = {
    '월세 -10%': mk(rent=lambda r: r['rent'] * 0.9), '월세 -5%': mk(rent=lambda r: r['rent'] * 0.95),
    '월세 +5%': mk(rent=lambda r: r['rent'] * 1.05), '월세 +10%': mk(rent=lambda r: r['rent'] * 1.10),
    '월세 x10 (500,000원을 만원으로 착각)': mk(rent=lambda r: r['rent'] * 10),
    '월세에 관리비 7만 합산': mk(rent=lambda r: r['rent'] + 7),
    '보증금 -50%': mk(dep=lambda r: r['dep'] * 0.5), '보증금 +50%': mk(dep=lambda r: r['dep'] * 1.5),
    '보증금 x10 (자리 오독)': mk(dep=lambda r: r['dep'] * 10), '보증금과 월세 맞바꿈(1000/50을 50/1000)': lambda r: {**r, 'dep': r['rent'], 'rent': r['dep']},
    '면적 -10%': mk(area=lambda r: r['area'] * 0.9), '면적 +10%': mk(area=lambda r: r['area'] * 1.1), '면적 +20%': mk(area=lambda r: r['area'] * 1.2),
    '면적 x1.3 (전용 대신 공급면적)': mk(area=lambda r: r['area'] * 1.3),
    '층 오류: 지상↔지하 뒤집기': mk(basement=lambda r: not bool(r['basement'])),
    '건물 유형 오류(연립↔단독, 오피스텔↔아파트)': usage_swap,
    '지번 삭제(동까지만 확인)': lot_drop, '지번 오매칭(같은 동 다른 건물)': lot_mismatch,
}

print('기준 판정 계산...', flush=True)
rows = [bases.iloc[i].to_dict() for i in range(len(bases))]
base_out = [judge(r) for r in rows]
base_rated = np.array([o['label'] != 'UNRATED' for o in base_out])
print(f'기준: 판정 가능 {base_rated.mean()*100:.1f}%  (대상 {len(rows)}건)', flush=True)

res = []
for name, fn in SCEN.items():
    n_rated0 = n_same = n_changed = n_held = n_new = n_flag = n_applied = 0
    n_s0_before = n_s0_after = n_wrong_lot = 0
    err_before, err_after = [], []
    for i, r in enumerate(rows):
        r2 = fn(r)
        if r2 is None:
            continue
        n_applied += 1
        o2 = judge(r2)
        o1 = base_out[i]
        flag = sanity_flag(r2, o2)
        n_flag += int(flag)
        was = o1['label'] != 'UNRATED'
        now = o2['label'] != 'UNRATED'
        if was:
            n_rated0 += 1
            if not now:
                n_held += 1
            elif o2['label'] == o1['label']:
                n_same += 1
            else:
                n_changed += 1
        elif now:
            n_new += 1
        if o1['rec']['source'] == 'STAGE0':
            n_s0_before += 1
        if o2['rec']['source'] == 'STAGE0':
            n_s0_after += 1
            if (r2.get('MNO'), r2.get('SNO')) != (r['MNO'], r['SNO']):
                n_wrong_lot += 1
        if o1['rec']['source'] != 'NONE':
            err_before.append(o1['rec']['err'])
        if o2['rec']['source'] != 'NONE':
            # 정확도는 '실제 월세' 기준(원본 값)으로 비교
            err_after.append(abs(o2['rec']['pred'] - r['rent']) / r['rent'])
    res.append(dict(scenario=name, applied=n_applied, rated_before=n_rated0,
                    label_same_pct=round(100 * n_same / max(n_rated0, 1), 1),
                    silent_wrong_label_pct=round(100 * n_changed / max(n_rated0, 1), 1),
                    held_pct=round(100 * n_held / max(n_rated0, 1), 1),
                    newly_rated_from_held=n_new,
                    sanity_flag_pct=round(100 * n_flag / max(n_applied, 1), 1),
                    stage0_wrong_building=n_wrong_lot,
                    median_err_before_pct=round(100 * float(np.median(err_before)), 2), median_err_after_pct=round(100 * float(np.median(err_after)), 2)))
    r_ = res[-1]
    print(f'{name}: 유지 {r_["label_same_pct"]}% / 다른 라벨 {r_["silent_wrong_label_pct"]}% / 보류 {r_["held_pct"]}% | 입력검증 포착 {r_["sanity_flag_pct"]}%'
          f' | 0단계 오진입 {r_["stage0_wrong_building"]} | 중앙오차 {r_["median_err_before_pct"]}→{r_["median_err_after_pct"]}%', flush=True)

# 입력 검증이 잡지 못하는(조용히 통과하는) 오류의 비율: 라벨이 바뀌었는데 검증 규칙에 걸리지 않은 경우를 따로 센다
out = INTERNAL / 'results' / f'input_errors_{datetime.now():%Y%m%d_%H%M%S}.json'
out.write_text(json.dumps(dict(n_bases=len(rows), baseline_rated_pct=round(100 * float(base_rated.mean()), 1), scenarios=res), ensure_ascii=False, indent=1), encoding='utf-8')
print('저장:', out)
