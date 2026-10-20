# -*- coding: utf-8 -*-
"""관리비 '상세보기' 창 캡처의 독립 평가. real/detail_new/NN.png (창이 보이는 화면, 연락처 가리기 불필요하면 창만 잘라도 됨)와
real/detail_new/labels.json 을 읽는다. labels.json 형식: {"01": {"total": 80000, "utility_included": ["수도","인터넷"], "utility_separate": [], "amounts": ["공용","전기"]}, ...}
(정답은 사람이 화면을 보고 작성. 파서·규칙을 고치기 전에 한 번만 평가하고, 고치면 이 세트는 개발용이 된다.)
지표: 카드 단위 — 총액 일치, 포함 공과금 일치, 별도 실비 일치, 항목금액 키 일치, 네 가지 모두 맞는 완전정답, 틀린 값 확정(오류) 수.
사용: set PYTHONPATH=_ocr_libs ; python eval_detail_new.py"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

import eval_ocr as E
from parse_detail import parse_detail

HERE = Path(__file__).resolve().parent
D = HERE / 'real' / 'detail_new'


def main():
    labels = json.loads((D / 'labels.json').read_text(encoding='utf-8'))
    eng = E.make_engine('easyocr')
    n = tot = inc = sep = amt = full = 0
    for k, lab in sorted(labels.items()):
        f = D / f'{k}.png'
        if not f.exists():
            continue
        p = parse_detail(' '.join(E.lines_from_boxes(eng(np.array(Image.open(f).convert('RGB'))))))
        a = p['total'] == lab['total']; b = p['utility_included'] == lab['utility_included']; c = p['utility_separate'] == lab['utility_separate']; d = sorted(p['amounts']) == sorted(lab['amounts'])
        n += 1; tot += a; inc += b; sep += c; amt += d; full += a and b and c and d
        if not (a and b and c and d):
            print('불일치', k, '읽음', p['total'], p['utility_included'], p['utility_separate'], sorted(p['amounts']), '정답', lab)
    print(f'[상세보기 독립 평가] {n}건: 총액 {tot}, 포함 공과금 {inc}, 별도 실비 {sep}, 항목금액 키 {amt}, 완전정답 {full}')


if __name__ == '__main__':
    main()
