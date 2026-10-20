# -*- coding: utf-8 -*-
"""하이브리드: Qwen2-VL 로 이미지의 글자를 그대로 전사 -> 규칙 파서(parse_ad_text)로 구조화. 숫자·단위는 모델이 아니라 규칙이 처리한다.
실행: python run_hybrid.py"""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
from parse_ad_text import parse_ad
import importlib.util

HERE = Path(__file__).resolve().parent
MODEL = HERE.parents[1] / 'data' / 'models' / 'Qwen2-VL-2B-Instruct'
IMG_DIR = HERE / 'synthetic'
PROMPT = '이 이미지에 보이는 모든 글자를 위에서 아래로 한 줄씩 그대로 옮겨 적으세요. 설명이나 해석 없이 글자만 출력하세요.'
spec = importlib.util.spec_from_file_location('mk', HERE / 'make_synthetic_ads.py')
mk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mk)


def transcribe(proc, model, path):
    img = Image.open(path).convert('RGB')
    msgs = [{'role': 'user', 'content': [{'type': 'image'}, {'type': 'text', 'text': PROMPT}]}]
    text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inp = proc(text=[text], images=[img], return_tensors='pt').to('cuda')
    with torch.no_grad():
        out = model.generate(**inp, max_new_tokens=300, do_sample=False)
    return proc.batch_decode(out[:, inp.input_ids.shape[1]:], skip_special_tokens=True)[0]


def main():
    proc = AutoProcessor.from_pretrained(str(MODEL), min_pixels=256 * 28 * 28, max_pixels=1024 * 28 * 28)
    model = Qwen2VLForConditionalGeneration.from_pretrained(str(MODEL), torch_dtype=torch.bfloat16, device_map='cuda')
    res, tally = {}, {}
    for i, (title, price, lines, truth) in enumerate(mk.CASES, 1):
        name = f'ad_{i:02d}'
        t = time.time()
        txt = transcribe(proc, model, IMG_DIR / f'{name}.png')
        r = parse_ad(txt)
        ok = {'deposit': r['deposit_10k_krw'] == truth['deposit'], 'rent': r['rent_10k_krw'] == truth['rent'],
              'maint': (r['maintenance_10k_krw'] is None and truth['maint'] is None) or (r['maintenance_10k_krw'] is not None and truth['maint'] is not None and abs(r['maintenance_10k_krw'] - truth['maint']) < 0.01),
              'included': sorted(r['maintenance_included_items']) == sorted(x.replace('청소비', '청소') for x in truth['included']),
              'area': r['area_m2'] == truth['area'], 'floor': r['floor'] == truth['floor']}
        for k, v in ok.items():
            tally[k] = tally.get(k, 0) + int(v)
        res[name] = dict(transcript=txt, parsed=r, ok=ok)
        print(name, f'{time.time()-t:.1f}s', [k for k, v in ok.items() if not v] or '전부 일치', flush=True)
        if not all(ok.values()):
            print('   전사:', txt.replace('\n', ' | ')[:260])
    n = len(mk.CASES)
    print('\n필드별 정확도:', {k: f'{v}/{n}' for k, v in tally.items()})
    (IMG_DIR / 'hybrid_results.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
