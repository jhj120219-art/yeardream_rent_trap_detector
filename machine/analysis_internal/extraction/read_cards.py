# -*- coding: utf-8 -*-
"""광고 목록 화면 이미지 → 카드 값 읽기 → 엔진 합의 → 확인용 초안 JSON (실행 가능한 파이프라인).
OCR 엔진(EasyOCR · PaddleOCR)을 직접 실행해 글자를 읽고, 카드를 **열(column)별로 먼저 나눈 뒤** 줄로 묶어 파서(`ad_cards.py`)에 넣고, 둘 이상이 같게 읽은 값만 `consensus.py` 로 채운다.
열 분리 이유: 같은 건물 매물이 가로 두 칸으로 보이는 화면에서 줄 묶기가 왼쪽 카드의 면적·관리비를 오른쪽 카드의 월세와 합쳐 세 엔진이 같은 오독을 했다.
시험 범위: 다방·직방 웹 목록 화면(다방 목록 열 폭 약 400px, 직방 360px)으로만 시험했다. 다른 앱 · 휴대폰 캡처 · 사진 속 글자는 아직 평가하지 않았다. 출력은 사용자 확인 전의 초안이며 `user_confirmed` 는 항상 false.
사용: python read_cards.py 이미지.png [--site dabang|zigbang] [--engines easyocr,paddle] [--crop x0,y0,x1,y1] [--out result.json]
OCR 패키지는 선택 설치(requirements-ocr.txt). 설치돼 있지 않으면 어떤 패키지가 필요한지 알려 주고 멈춘다."""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ad_cards import cards_from as _cards_from, cards_from_zigbang as _cards_from_zigbang  # noqa: E402
from consensus import consensus  # noqa: E402
from partial_fields import TILE_MARK, image_fields, merge_image_fields, partial_cards  # noqa: E402

KEY = lambda c: (c[0], c[1], c[2], c[4], c[5])        # (종류, 보증금, 월세, 면적, 관리비)
SPLIT_RATIO = 0.4875                                  # 크롭 폭 400px 에서 왼쪽 열 경계 x=195 (다방 웹 목록 기준)


def norm(text):
    """OCR 이 자주 바꾸는 키워드·단위 표기만 정규화한다. 숫자 값·소수점·전세/월세 구분은 건드리지 않는다."""
    t = re.sub(r'[훨윌원]세(?=\s*[\d억])', '월세', text)
    t = re.sub(r'(?<=\d)[증총흥](?=\s*[,\s]*\d)', '층', t)
    t = re.sub(r'(?<=\d)\s*(?:m|rn|mz|mn|mㅡ|ㅡ)\s*[2²?]?(?=\s*[,\s]|$)', 'm²', t)
    t = re.sub(r'(?<=\d)\s*㎡', 'm²', t)
    return t


def norm_zigbang(t):
    """직방 목록용 정규화(키워드·단위 표기만)."""
    t = re.sub(r'[훨윌원]세(?=\s*[\d억])', '월세', t)
    t = re.sub(r'(?<=\d)[증총흥](?=\s|$)', '층', t)
    t = re.sub(r'(?<=\d)\s*(?:rn|mz|mn|m\?|m)\s*[2²?]?(?=\s|$|・|·)', 'm²', t)
    t = re.sub(r'관리비\s*([\d\.]+)\s*(?:만원|만 원|만윈|만웬)', lambda m: '관리비 ' + m.group(1) + '만원', t)
    return t


ZB_CROP = (1040, 200, 1400, 4200)                     # 직방 웹 목록 열(폭 360px, 한 열 카드) 기준
ZB_TILE, ZB_STEP = 900, 600                           # 직방은 겹치는 조각(높이 900, 간격 600)으로 나눠 읽는다


def lines_from_boxes(res):
    """[(box, text, conf)] → 줄 단위 텍스트. 같은 줄 = 박스 세로 중심이 가깝다."""
    items = []
    for b, t, c in res:
        ys = [p[1] for p in b]
        xs = [p[0] for p in b]
        items.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), t))
    items.sort()
    lines, cur, cy = [], [], None
    for y, h, x, t in items:
        if cur and abs(y - cy) > 0.6 * max(h, 10):
            lines.append(cur)
            cur = []
        if not cur:
            cy = y
        cur.append((x, t))
    if cur:
        lines.append(cur)
    return ['  '.join(t for x, t in sorted(l)) for l in lines]


def lines_by_column(res, width):
    """박스를 왼쪽 열 / 오른쪽 열로 먼저 나눈 뒤 각각 줄로 묶어 이어 붙인다(오른쪽 열 카드와 왼쪽 열 카드가 한 줄로 섞이지 않게)."""
    split = width * SPLIT_RATIO
    left = [r for r in res if min(p[0] for p in r[0]) < split]
    right = [r for r in res if min(p[0] for p in r[0]) >= split]
    return lines_from_boxes(left) + lines_from_boxes(right)


def text_by_column(res, width):
    return norm('\n'.join(lines_by_column(res, width)))


def cards_from_boxes(res, width, partial=True):
    """partial=True(기본): 면적·관리비가 없는 카드도 읽은 항목만 살려 읽는다(없는 항목 None). partial=False: 예전처럼 항목이 모두 있는 카드만."""
    text = text_by_column(res, width)
    if partial:
        return set(partial_cards(text))
    return {KEY(c) for c in _cards_from(text)}


def zigbang_text(tile_results):
    return norm_zigbang((chr(10) + TILE_MARK + chr(10)).join(chr(10).join(lines_from_boxes(r)) for r in tile_results))


def cards_from_zigbang_boxes(tile_results, partial=True):
    """조각별 OCR 결과 리스트 → 직방 카드 값. 직방 목록은 한 열이라 열 분리를 쓰지 않는다."""
    text = zigbang_text(tile_results)
    if partial:
        return set(partial_cards(text))
    return {KEY(c) for c in _cards_from_zigbang(text)}


def make_engine(name):
    try:
        if name == 'easyocr':
            import easyocr
            r = easyocr.Reader(['ko', 'en'], gpu=False)
            return lambda arr: r.readtext(arr)
        if name == 'paddle':
            from paddleocr import PaddleOCR
            r = PaddleOCR(lang='korean', ocr_version='PP-OCRv5', use_doc_orientation_classify=False, use_doc_unwarping=False,
                          use_textline_orientation=False, enable_mkldnn=False)

            def f(arr):
                out = []
                for page in r.predict(arr):
                    for poly, t, c in zip(page['rec_polys'], page['rec_texts'], page['rec_scores']):
                        out.append(([list(map(float, pt)) for pt in poly], t, float(c)))
                return out
            return f
    except ImportError as e:
        raise SystemExit(f'OCR 패키지가 필요합니다({name}): {e}. requirements-ocr.txt 를 설치하세요.') from None
    raise SystemExit('지원하는 엔진: easyocr, paddle')


def read_image(path, engines=('easyocr', 'paddle'), crop=None, engine_factory=make_engine, site='dabang'):
    import numpy as np
    from PIL import Image
    img = Image.open(path).convert('RGB')
    if site == 'zigbang':
        img = img.crop(crop or ZB_CROP)
        reads, texts = {}, {}
        for name in engines:
            eng = engine_factory(name)
            tiles = [eng(np.array(img.crop((0, y, img.width, min(y + ZB_TILE, img.height))))) for y in range(0, max(img.height - 200, 1), ZB_STEP)]
            texts[name] = zigbang_text(tiles)
            reads[name] = sorted(set(partial_cards(texts[name])), key=repr)
        return {'engine_reads': reads, 'cards': consensus(reads), 'image_fields': merge_image_fields({e: image_fields(t) for e, t in texts.items()}),
            'image_fields_by_engine': {e: image_fields(t) for e, t in texts.items()}}
    if site != 'dabang':
        raise SystemExit('지원하는 사이트: dabang, zigbang')
    if crop:
        img = img.crop(crop)
    arr = np.array(img)
    raw = {name: engine_factory(name)(arr) for name in engines}
    texts = {name: text_by_column(r, img.width) for name, r in raw.items()}
    reads = {name: sorted(set(partial_cards(t)), key=repr) for name, t in texts.items()}
    return {'engine_reads': reads, 'cards': consensus(reads), 'image_fields': merge_image_fields({e: image_fields(t) for e, t in texts.items()}),
            'image_fields_by_engine': {e: image_fields(t) for e, t in texts.items()}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('image')
    ap.add_argument('--engines', default='easyocr,paddle')
    ap.add_argument('--site', default='dabang', choices=['dabang', 'zigbang'], help='목록 화면 종류(기본 dabang). 직방은 --crop 을 생략하면 1040,200,1400,4200')
    ap.add_argument('--crop', help='x0,y0,x1,y1 (다방 웹 캡처: 80,170,480,3600)')
    ap.add_argument('--out')
    a = ap.parse_args(argv)
    crop = tuple(int(v) for v in a.crop.split(',')) if a.crop else None
    result = read_image(a.image, tuple(a.engines.split(',')), crop, site=a.site)
    s = {k: sum(c['status'] == k for c in result['cards']) for k in ('extracted', 'needs_review', 'on_hold')}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if a.out:
        Path(a.out).write_text(text, encoding='utf-8')
    print(f'엔진 {a.engines}: 자동 입력 후보 {s["extracted"]}개, 확인 필요 {s["needs_review"]}개, 보류 {s["on_hold"]}개 (모두 사용자 확인 전 초안)')
    for c in result['cards']:
        if c['status'] == 'extracted':
            f = c['fields']
            print('  ', f['contract_type']['value'], f['deposit_10k_krw']['value'], '/', f['rent_10k_krw']['value'], '|', f['area_m2']['value'], '㎡ | 관리비', f['maintenance_10k_krw']['value'], '만원',
                  c['warnings'] or '')
    if not a.out:
        print('(--out 으로 전체 JSON 저장)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
