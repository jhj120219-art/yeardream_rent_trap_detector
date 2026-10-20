# -*- coding: utf-8 -*-
"""홀드아웃 2(송파·강북) 데이터 정제 + 기준 매물 선정 + 건축HUB 조회 대상 지번 목록 생성.
설계 데이터와 같은 정제(compare_rent.clean)·같은 기준 매물 규칙(구별 최근 3개월 신규 1,500건, 시드 7)을 쓴다.
출력: output/holdout2_clean.csv, data/holdout2/base_lots.csv (기준 매물이 속한 비단독 지번)
주의: 이 스크립트는 정확도를 계산하지 않는다(성능은 --frozen 평가에서 1회만).
"""
import glob
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import ROOT, np, pd, load_policy, make_bases
import compare_rent as cr

policy = load_policy()
parts = []
for f in sorted(glob.glob(str(ROOT / 'data' / 'holdout2' / 'rent_*_2025_2026.csv'))):
    r, rep = cr.clean(pd.read_csv(f, dtype=str))
    parts.append(r)
    print(Path(f).name, '정제 후 월세', rep['정제 후 월세'], '신규', rep['  정제 후 신규(비교 풀)'])
rent = pd.concat(parts, ignore_index=True)
assert set(rent['gu']) == {'송파구', '강북구'}, set(rent['gu'])
rent.to_csv(ROOT / 'output' / 'holdout2_clean.csv', index=False, encoding='utf-8-sig')
ev = policy['evaluation']
rent['is_new'] = rent['is_new'].astype(bool)
bases = make_bases(rent, ev['seed'], ev['bases_per_gu'], ev['recent_months'])
print('기준 매물', len(bases), bases.groupby('gu').size().to_dict(), '용도', bases['usage'].value_counts().to_dict())
b = bases[(bases['usage'] != '단독다가구') & bases['MNO'].notna() & bases['SNO'].notna()]
lots = b.drop_duplicates(['CGG_CD', 'STDG_CD', 'MNO', 'SNO'])[['CGG_CD', 'STDG_CD', 'MNO', 'SNO']]
lots.to_csv(ROOT / 'data' / 'holdout2' / 'base_lots.csv', index=False, encoding='utf-8-sig')
print('기준 매물이 속한 비단독 지번', len(lots))
