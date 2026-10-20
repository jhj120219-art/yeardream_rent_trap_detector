# -*- coding: utf-8 -*-
"""광고 이미지 -> 구조화 JSON (Qwen2-VL-2B-Instruct, 무학습 추론). 합성 광고(synthetic/)에서 정답과 비교한다.
카드/영수증 스캔 자동 입력과 같은 흐름: 이미지 -> 필드 추출(원문 근거 포함) -> 사용자 확인 -> 점검 모듈.
실행: python run_qwen2vl.py [이미지 폴더]"""
import json
import re
import sys
import time
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

HERE = Path(__file__).resolve().parent
MODEL = HERE.parents[1] / 'data' / 'models' / 'Qwen2-VL-2B-Instruct'
IMG_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / 'synthetic'

PROMPT = """이 이미지는 월세 매물 광고 화면입니다. 광고에 적힌 내용만 읽어서 아래 JSON 하나만 출력하세요. 추측하지 말고 적혀 있지 않으면 null 로 두세요.
{
 "deposit_10k_krw": 보증금(만원 단위 숫자, '1억'은 10000),
 "rent_10k_krw": 월세(만원 단위 숫자),
 "maintenance_10k_krw": 관리비(만원 단위 숫자, '7만원'은 7, '5.5만원'은 5.5, 관리비 금액이 없으면 null, '없음'이면 0),
 "maintenance_included_items": 관리비에 포함된다고 적힌 항목 목록(예: ["수도","인터넷","청소"]),
 "maintenance_excluded_items": 별도 또는 불포함이라고 적힌 항목 목록,
 "area_m2": 면적 숫자(전용면적이 있으면 전용),
 "area_basis": "전용" 또는 "공급" 또는 null,
 "floor": 층 문구 그대로(예: "3", "반지하"),
 "address_text": 주소 문구,
 "evidence": {"price": 가격 원문, "maintenance": 관리비 원문}
}"""


def load():
    proc = AutoProcessor.from_pretrained(str(MODEL), min_pixels=256 * 28 * 28, max_pixels=1024 * 28 * 28)
    model = Qwen2VLForConditionalGeneration.from_pretrained(str(MODEL), torch_dtype=torch.bfloat16, device_map='cuda')
    return proc, model


def extract(proc, model, path):
    img = Image.open(path).convert('RGB')
    msgs = [{'role': 'user', 'content': [{'type': 'image'}, {'type': 'text', 'text': PROMPT}]}]
    text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inp = proc(text=[text], images=[img], return_tensors='pt').to('cuda')
    with torch.no_grad():
        out = model.generate(**inp, max_new_tokens=400, do_sample=False)
    raw = proc.batch_decode(out[:, inp.input_ids.shape[1]:], skip_special_tokens=True)[0]
    m = re.search(r'\{.*\}', raw, re.S)
    try:
        return json.loads(m.group(0)), raw
    except Exception:
        return None, raw


def norm_items(x):
    return sorted({str(i).replace('비', '') if str(i) == '청소비' else str(i) for i in (x or [])})


def main():
    gt = json.loads((IMG_DIR / 'ground_truth.json').read_text(encoding='utf-8'))
    t0 = time.time()
    proc, model = load()
    print(f'모델 로드 {time.time()-t0:.0f}s', flush=True)
    rows, res = [], {}
    for name, truth in gt.items():
        t1 = time.time()
        js, raw = extract(proc, model, IMG_DIR / f'{name}.png')
        res[name] = dict(extracted=js, raw=raw)
        ok = {}
        if js:
            ok['deposit'] = js.get('deposit_10k_krw') == truth['deposit']
            ok['rent'] = js.get('rent_10k_krw') == truth['rent']
            mt = js.get('maintenance_10k_krw')
            ok['maint'] = (mt is None and truth['maint'] is None) or (mt is not None and truth['maint'] is not None and abs(float(mt) - truth['maint']) < 0.01)
            ok['included'] = norm_items(js.get('maintenance_included_items')) == norm_items(truth['included'])
            ar = js.get('area_m2')
            ok['area'] = ar is not None and abs(float(ar) - truth['area']) < 0.01
            ok['floor'] = str(js.get('floor', '')).replace('층', '') .strip() in (truth['floor'], truth['floor'] + '층')
        rows.append((name, ok))
        print(name, f'{time.time()-t1:.1f}s', ok if js else 'JSON 파싱 실패', flush=True)
        if js is None:
            print('  raw:', raw[:300])
    fields = ['deposit', 'rent', 'maint', 'included', 'area', 'floor']
    print('\n필드별 정확도:')
    for f in fields:
        n = sum(1 for _, o in rows if o.get(f))
        print(f'  {f}: {n}/{len(rows)}')
    allok = sum(1 for _, o in rows if o and all(o.get(f) for f in fields[:4]))
    print(f'금액·관리비·포함항목 모두 일치: {allok}/{len(rows)}')
    (HERE / 'synthetic' / 'qwen2vl_results.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
