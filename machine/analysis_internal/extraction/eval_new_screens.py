# -*- coding: utf-8 -*-
"""설정(조각 높이 560, 간격 200)을 고정한 뒤, 개발에 쓰지 않은 다른 구 화면(real/new_*.png)에서 독립 평가.
정답 = 같은 화면의 DOM 텍스트. 지표: 처리율, 처리된 카드 정확도, 완전정답률(월세·보증금·면적·관리비 모두 일치).
사용: python eval_new_screens.py"""
import sys
import time
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

from eval_real_list import MODEL, PROMPT, cards_from

HERE = Path(__file__).resolve().parent
STEP, H = 200, 560


def main():
    proc = AutoProcessor.from_pretrained(str(MODEL), min_pixels=256 * 28 * 28, max_pixels=1280 * 28 * 28)
    model = Qwen2VLForConditionalGeneration.from_pretrained(str(MODEL), torch_dtype=torch.bfloat16, device_map='cuda')
    old = {(c[0], c[1], c[2], c[4], c[5]) for c in cards_from((HERE / 'real' / 'dabang_list_tall_dom.txt').read_text(encoding='utf-8'))}
    G, F, WR, ALLFOUND = set(), set(), {}, set()
    for n in range(1, 6):
        img = Image.open(HERE / 'real' / f'new_{n}.png').convert('RGB')
        gt = cards_from((HERE / 'real' / f'new_{n}_dom.txt').read_text(encoding='utf-8'))
        key = lambda c: (c[0], c[1], c[2], c[4], c[5])
        gset = {key(c) for c in gt}
        found, raws = [], []
        y = 170
        while y < 3600 - 200:
            crop = img.crop((80, y, 480, min(y + H, 3600)))
            for q in (PROMPT, '이 이미지에 적힌 한국어 글자를 줄 단위로 그대로 적어 주세요.'):
                msgs = [{'role': 'user', 'content': [{'type': 'image'}, {'type': 'text', 'text': q}]}]
                text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
                inp = proc(text=[text], images=[crop], return_tensors='pt').to('cuda')
                with torch.no_grad():
                    out = model.generate(**inp, max_new_tokens=500, do_sample=False)
                raw = proc.batch_decode(out[:, inp.input_ids.shape[1]:], skip_special_tokens=True)[0]
                if cards_from(raw) or '관리비' in raw:
                    break
            raws.append(raw)
            for c in cards_from(raw):
                if c not in found:
                    found.append(c)
            y += STEP
        fset = {key(c) for c in found}
        hit, wrong = gset & fset, fset - gset
        G |= gset; F |= fset; ALLFOUND |= fset
        print(f'화면{n}: 정답카드 {len(gset)} 맞게 읽음 {len(hit)} 읽은 카드 {len(fset)} 틀리게 읽음 {len(wrong)}', flush=True)
        for w in sorted(wrong)[:4]:
            print('   오독:', w, flush=True)
        for m in sorted(gset - fset)[:3]:
            print('   못읽음:', m, flush=True)
    G -= old
    hit = G & F
    wrong = {c for c in F if c not in G and c not in old}
    print(f'독립 카드(화면 간·기존 화면과 중복 제거) {len(G)}개: 완전정답 {len(hit)} ({len(hit)/len(G):.0%}), 읽은 카드 {len(hit)+len(wrong)} 중 틀림 {len(wrong)}')
    for w in sorted(wrong, key=str)[:12]:
        print('   오독:', w)
    for m in sorted(G - F, key=str)[:12]:
        print('   못읽음:', m)

if __name__ == '__main__':
    main()
