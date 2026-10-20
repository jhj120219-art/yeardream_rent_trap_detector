# -*- coding: utf-8 -*-
"""EasyOCR(정규화·범위검사 규칙 고정) 홀드아웃 평가. 규칙을 만든 화면(dabang_list_tall, new_1~5)의 카드는 제외하고,
ind_11~18 화면에서만 나온 새 카드로 평가한다. 이 결과를 보고 규칙을 고치면 이 세트도 개발용이 된다.
사용: set PYTHONPATH=_ocr_libs ; python eval_ocr_holdout.py"""
from pathlib import Path

import numpy as np
from PIL import Image

import eval_ocr as E
from ad_cards import cards_from as strict

HERE = E.HERE


import sys


def main(name='easyocr'):
    eng = E.make_engine(name)
    dev = set()
    for f in ['dabang_list_tall'] + [f'new_{n}' for n in range(1, 6)]:
        dev |= {E.KEY(c) for c in strict((HERE / 'real' / f'{f}_dom.txt').read_text(encoding='utf-8'))}
    G, F = set(), set()
    for n in range(11, 19):
        img = Image.open(HERE / 'real' / f'ind_{n}.png').convert('RGB').crop((80, 170, 480, 3600))
        txt = '\n'.join(E.lines_from_boxes(eng(np.array(img))))
        G |= {E.KEY(c) for c in strict((HERE / 'real' / f'ind_{n}_dom.txt').read_text(encoding='utf-8'))}
        F |= {E.KEY(c) for c in E.cards_from(txt)}
    import json
    (HERE / 'real' / f'holdout_{name}_reads.json').write_text(json.dumps([list(c) for c in sorted(F, key=str)], ensure_ascii=False), encoding='utf-8')
    G -= dev
    hit = G & F
    wrong = {c for c in F if c not in G and c not in dev}
    print(f'[홀드아웃 {name}] 새 카드 {len(G)}개: 완전정답 {len(hit)} ({len(hit)/len(G):.0%}), 읽은 카드 {len(hit)+len(wrong)} 중 틀림 {len(wrong)}, 보류(못 읽음) {len(G-F)}')
    for w in sorted(wrong, key=str):
        print('   오독:', w)


if __name__ == '__main__':
    main(*sys.argv[1:2])
