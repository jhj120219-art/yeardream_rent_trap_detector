# -*- coding: utf-8 -*-
"""목록 카드 텍스트 -> (종류, 보증금, 월세, 층, 면적, 관리비) 파서와 비정상 범위 보류 규칙. 모델·OCR 평가 스크립트가 공유한다."""
import re

BAD = float("nan")
HEAD = re.compile(r'(월세|원세|전세)\s*([\d억,\.]+)(?:\s*/\s*([\d,\.]+))?')
BODY = re.compile(r'(\S+층|고층|중층|저층|반지하|반지층|옥탑)[,\s]*([\d\.]+)\s*[mM㎡][²2]?[,\s]*관리비\s*([\d\.]+)\s*만')


def won(s):
    s = s.replace(',', '')
    m = re.fullmatch(r'(\d+)억(\d*)', s)
    if m:
        return float(m.group(1)) * 10000 + (float(m.group(2)) if m.group(2) else 0)
    try:
        return float(s) if s else None
    except ValueError:                      # 금액 자리에 숫자가 아닌 글자(예: '.')가 섞이면 읽지 않고 보류
        return BAD


def cards_from(text):
    """카드 단위로 자른 뒤(월세/전세 표기가 나올 때마다 새 카드) 각 카드 안에서만 읽는다. 카드 경계를 넘어 다음 카드와 섞이지 않는다.
    관리비가 '없음' 등 숫자가 아닌 카드, 금액·면적 자리에 숫자가 아닌 글자가 섞인 카드는 읽지 않고 건너뛴다(보류)."""
    out = []
    for blk in re.split(r'(?=(?:월세|원세|전세)\s*[\d억])', text.replace(chr(10), ' ')):
        h = HEAD.match(blk.strip())
        b = BODY.search(blk)
        if not h or not b:
            continue
        try:
            area, maint = float(b.group(2)), float(b.group(3))
        except ValueError:
            continue
        rent, mon = won(h.group(2)), won(h.group(3) or '')
        if rent is BAD or mon is BAD:
            continue
        if not (3 <= area <= 300 and rent <= 100000 and (mon is None or mon <= 2000) and maint <= 100):   # 비정상 범위(소수점 누락 등)는 읽지 않고 보류 → 사용자 확인
            continue
        out.append(('월세' if h.group(1) == '원세' else h.group(1), rent, mon, b.group(1), area, maint))
    return out
