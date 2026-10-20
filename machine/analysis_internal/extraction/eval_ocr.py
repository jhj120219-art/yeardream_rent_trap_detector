# -*- coding: utf-8 -*-
"""OCR 엔진별 비교: eval_new_screens.py 와 같은 5개 화면·같은 정답(DOM)·같은 카드 파서(cards_from)로 평가한다.
엔진: easyocr (이후 rapidocr 등 추가). 화면을 조각 없이 목록 영역(x 80-480, y 170-3600) 한 장으로 OCR 하고, 박스를 줄로 묶어 파서에 넣는다.
후처리 없음(소수점·전세/월세 보정 금지). 사용: set PYTHONPATH=_ocr_libs ; python eval_ocr.py easyocr"""
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

import re

from ad_cards import cards_from as _cards_from

HERE = Path(__file__).resolve().parent
KEY = lambda c: (c[0], c[1], c[2], c[4], c[5])


def norm(text):
    """OCR 이 자주 바꾸는 키워드·단위 표기만 정규화한다. 숫자 값·소수점·전세/월세 구분은 건드리지 않는다."""
    t = re.sub(r'[훨윌원]세(?=\s*[\d억])', '월세', text)                       # '월세' 글자 혼동(키워드)
    t = re.sub(r'(?<=\d)[증총흥](?=\s*[,\s]*\d)', '층', t)                     # '층' 글자 혼동
    t = re.sub(r'(?<=\d)\s*(?:m|rn|mz|mn|mㅡ|ㅡ)\s*[2²?]?(?=\s*[,\s]|$)', 'm²', t)   # 단위 m² 혼동
    t = re.sub(r'(?<=\d)\s*㎡', 'm²', t)
    return t


def cards_from(text):
    return _cards_from(norm(text))


def lines_from_boxes(res):
    """[(box, text, conf)] -> 줄 단위 텍스트. 같은 줄 = 박스 세로 중심이 가깝다."""
    items = []
    for b, t, c in res:
        ys = [p[1] for p in b]; xs = [p[0] for p in b]
        items.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), t))
    items.sort()
    lines, cur, cy = [], [], None
    for y, h, x, t in items:
        if cur and abs(y - cy) > 0.6 * max(h, 10):
            lines.append(cur); cur = []
        cur.append((x, t)); cy = y if not cur[:-1] else cy
    if cur:
        lines.append(cur)
    return ['  '.join(t for x, t in sorted(l)) for l in lines]


def make_engine(name):
    if name == 'easyocr':
        import easyocr
        r = easyocr.Reader(['ko', 'en'], gpu=True, model_storage_directory=str(HERE / '_ocr_libs' / 'easyocr_models'), download_enabled=False)
        return lambda arr: r.readtext(arr)
    if name == 'paddle':
        from paddleocr import PaddleOCR
        r = PaddleOCR(lang='korean', ocr_version='PP-OCRv5', use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False, enable_mkldnn=False)
        def f(arr):
            out = []
            for page in r.predict(arr):
                for poly, t, c in zip(page['rec_polys'], page['rec_texts'], page['rec_scores']):
                    out.append(([list(map(float, pt)) for pt in poly], t, float(c)))
            return out
        return f
    if name == 'rapidocr':
        from rapidocr_onnxruntime import RapidOCR
        r = RapidOCR()
        def f(arr):
            out, _ = r(arr)
            return [(b, t, c) for b, t, c in (out or [])]
        return f
    raise SystemExit('unknown engine')


def main(name):
    eng = make_engine(name)
    old = {KEY(c) for c in cards_from((HERE / 'real' / 'dabang_list_tall_dom.txt').read_text(encoding='utf-8'))}
    G, F = set(), set()
    t0 = time.time()
    dump = []
    for n in range(1, 6):
        img = Image.open(HERE / 'real' / f'new_{n}.png').convert('RGB').crop((80, 170, 480, 3600))
        res = eng(np.array(img))
        txt = '\n'.join(lines_from_boxes(res))
        dump.append(txt)
        G |= {KEY(c) for c in cards_from((HERE / 'real' / f'new_{n}_dom.txt').read_text(encoding='utf-8'))}
        F |= {KEY(c) for c in cards_from(txt)}
    (HERE / 'real' / f'ocr_{name}_text.txt').write_text('\n=====\n'.join(dump), encoding='utf-8')
    G -= old
    hit = G & F
    wrong = {c for c in F if c not in G and c not in old}
    print(f'[{name}] {time.time()-t0:.0f}s  독립 카드 {len(G)}개: 완전정답 {len(hit)} ({len(hit)/len(G):.0%}), 읽은 카드 {len(hit)+len(wrong)} 중 틀림 {len(wrong)}')
    for w in sorted(wrong, key=str)[:10]:
        print('   오독:', w)
    for m in sorted(G - F, key=str)[:10]:
        print('   못읽음:', m)


if __name__ == '__main__':
    main(sys.argv[1])
