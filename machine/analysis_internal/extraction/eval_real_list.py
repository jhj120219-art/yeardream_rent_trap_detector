# -*- coding: utf-8 -*-
"""실제 다방 목록 화면 캡처(1400x3600, 사용자 PC에서 본 화면)를 Qwen2-VL 로 전사하고 카드별 월세·보증금·면적·관리비를 읽어,
같은 화면의 DOM 텍스트(정답)와 비교한다. 실제 화면 한 장 기준의 소규모 확인이며 일반화 정확도가 아니다.
사용: python eval_real_list.py"""
import re
import sys
import time
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

from ad_cards import BAD, cards_from, won  # noqa: F401

HERE = Path(__file__).resolve().parent
MODEL = HERE.parents[1] / 'data' / 'models' / 'Qwen2-VL-2B-Instruct'
IMG = HERE / 'real' / 'dabang_list_tall.png'
DOM = HERE / 'real' / 'dabang_list_tall_dom.txt'
PROMPT = '이 이미지는 부동산 앱의 매물 목록 일부입니다. 보이는 모든 글자를 위에서 아래로 한 줄씩 그대로 옮겨 적으세요. 설명 없이 글자만 출력하세요.'
def main():
    gt_txt = DOM.read_text(encoding='utf-8')
    i = gt_txt.index('월세 500/40')
    gt = cards_from(gt_txt[i:i + 9000])
    print('정답(DOM) 카드', len(gt))
    proc = AutoProcessor.from_pretrained(str(MODEL), min_pixels=256 * 28 * 28, max_pixels=1280 * 28 * 28)
    model = Qwen2VLForConditionalGeneration.from_pretrained(str(MODEL), torch_dtype=torch.bfloat16, device_map='cuda')
    img = Image.open(IMG).convert('RGB')
    x0, x1, y0, y1 = 80, 480, 170, 3600
    found, raw_all = [], []
    step, h = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (200, 560)
    y = y0
    t0 = time.time()
    while y < y1 - 200:
        crop = img.crop((x0, y, x1, min(y + h, y1)))
        msgs = [{'role': 'user', 'content': [{'type': 'image'}, {'type': 'text', 'text': PROMPT}]}]
        text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inp = proc(text=[text], images=[crop], return_tensors='pt').to('cuda')
        with torch.no_grad():
            out = model.generate(**inp, max_new_tokens=500, do_sample=False)
        raw = proc.batch_decode(out[:, inp.input_ids.shape[1]:], skip_special_tokens=True)[0]
        if not cards_from(raw) and '관리비' not in raw:      # 좌표만 돌려주는 등 실패한 조각은 다른 문구로 한 번 더 시도
            msgs2 = [{'role': 'user', 'content': [{'type': 'image'}, {'type': 'text', 'text': '이 이미지에 적힌 한국어 글자를 줄 단위로 그대로 적어 주세요.'}]}]
            text2 = proc.apply_chat_template(msgs2, tokenize=False, add_generation_prompt=True)
            inp2 = proc(text=[text2], images=[crop], return_tensors='pt').to('cuda')
            with torch.no_grad():
                out2 = model.generate(**inp2, max_new_tokens=500, do_sample=False)
            raw = proc.batch_decode(out2[:, inp2.input_ids.shape[1]:], skip_special_tokens=True)[0]
        raw_all.append(raw)
        for c in cards_from(raw):
            if c not in found:
                found.append(c)
        y += step
    print(f'전사 {len(raw_all)}조각, {time.time()-t0:.0f}s, 읽은 카드(중복 제거) {len(found)}')
    gset = {(c[0], c[1], c[2], c[4], c[5]) for c in gt}
    fset = {(c[0], c[1], c[2], c[4], c[5]) for c in found}
    hit = gset & fset
    print(f'정답 카드 중 월세/보증금·면적·관리비가 모두 일치하게 읽은 수: {len(hit)}/{len(gset)}')
    gm = {(c[4]): c for c in gt}
    maint_ok = sum(1 for c in found if any(abs(c[5] - g[5]) < 0.01 and abs(c[4] - g[4]) < 0.01 for g in gt))
    print(f'읽은 카드 중 (면적, 관리비)가 정답과 일치: {maint_ok}/{len(found)}')
    miss = [c for c in gt if (c[0], c[1], c[2], c[4], c[5]) not in fset]
    print('못 읽은/틀린 정답 카드:', miss[:12])
    if len(sys.argv) <= 2: (HERE / 'real' / 'dabang_list_transcripts.txt').write_text('\n=====\n'.join(raw_all), encoding='utf-8')


if __name__ == '__main__':
    main()
