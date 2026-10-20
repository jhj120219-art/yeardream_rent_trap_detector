# -*- coding: utf-8 -*-
"""홀드아웃 46카드에서 엔진 조합 비교(저장된 읽기 결과 사용). 규칙: 합의=두 엔진이 같은 값, 합집합=어느 한쪽이 읽으면 채택.
사용: python eval_ensemble_holdout.py"""
import json
from pathlib import Path

from ad_cards import cards_from

HERE = Path(__file__).resolve().parent
K = lambda c: (c[0], c[1], c[2], c[4], c[5])
dev = set()
for f in ['dabang_list_tall'] + [f'new_{n}' for n in range(1, 6)]:
    dev |= {K(c) for c in cards_from((HERE / 'real' / f'{f}_dom.txt').read_text(encoding='utf-8'))}
G = set()
for n in range(11, 19):
    G |= {K(c) for c in cards_from((HERE / 'real' / f'ind_{n}_dom.txt').read_text(encoding='utf-8'))}
G -= dev
R = {e: {tuple(x) for x in json.loads((HERE / 'real' / f'holdout_{e}_reads.json').read_text(encoding='utf-8'))} - dev for e in ('easyocr', 'paddle', 'qwen')}


def show(name, F):
    hit = G & F
    print(f'{name:28s} 완전정답 {len(hit):2d}/{len(G)} ({len(hit)/len(G):.0%})  읽은 {len(F):2d}건 중 틀림 {len(F-G):2d}  보류 {len(G-F)}')


for e in R:
    show(e, R[e])
show('easyocr ∩ paddle (합의)', R['easyocr'] & R['paddle'])
show('easyocr ∩ qwen (합의)', R['easyocr'] & R['qwen'])
show('paddle ∩ qwen (합의)', R['paddle'] & R['qwen'])
show('paddle ∪ easyocr (합집합)', R['paddle'] | R['easyocr'])
show('2개 이상 일치(다수결)', {c for c in R['easyocr'] | R['paddle'] | R['qwen'] if sum(c in R[e] for e in R) >= 2})


print('\n--- 카드 단위 집계(정답 카드 46개 각각을 하나로 분류: 맞게/틀리게/못 읽음. 틀린 읽기는 면적·관리비가 같은 정답 카드에 귀속) ---')
by_ak = {}
for g in G:
    by_ak.setdefault((g[3], g[4]), []).append(g)


def per_card(F):
    ok = wrong = 0
    attributed = set()
    for g in G:
        if g in F:
            ok += 1
        else:
            cand = [f for f in F if (f[3], f[4]) == (g[3], g[4]) and f not in G]
            if cand:
                wrong += 1
    unread = len(G) - ok - wrong
    stray = len([f for f in F if f not in G and (f[3], f[4]) not in by_ak])   # 정답 카드와 연결되지 않는 틀린 읽기(면적·관리비가 다른 값)
    return ok, wrong, unread, stray


for name, F in [('easyocr', R['easyocr']), ('paddle', R['paddle']), ('qwen', R['qwen']), ('2개 이상 일치', {c for c in R['easyocr'] | R['paddle'] | R['qwen'] if sum(c in R[e] for e in R) >= 2})]:
    ok, wrong, unread, stray = per_card(F)
    print(f'{name:14s} 맞게 {ok:2d}  틀리게 {wrong:2d}  못 읽음 {unread:2d}  (합 {ok+wrong+unread}/{len(G)})  정답 카드와 연결 안 되는 틀린 읽기 {stray}')
