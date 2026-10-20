# -*- coding: utf-8 -*-
"""광고 문구(OCR/전사 텍스트) -> 구조화 필드. 숫자·단위·포함/별도 판단은 규칙으로 처리해 모델의 단위 오류를 피한다.
모호하면 값을 추정하지 않고 None(확인 필요)으로 둔다."""
import re

ITEMS = ['공용전기', '전기', '수도', '가스', '난방', '인터넷', '청소', '공과금', '승강기', 'TV', '케이블']


def _won10k(s):
    """'2,000만원' '1억' '7만원' '5.5만원' '500' -> 만원 단위 float. 해석 불가면 None."""
    s = re.sub(r'[\s,]+', '', s)
    m = re.fullmatch(r'(\d+(?:\.\d+)?)억(?:(\d+(?:\.\d+)?)천?만?)?원?', s)
    if m:
        return float(m.group(1)) * 10000 + (float(m.group(2)) if m.group(2) else 0)
    m = re.fullmatch(r'(\d+(?:\.\d+)?)천만원?', s)
    if m:
        return float(m.group(1)) * 1000
    m = re.fullmatch(r'(\d+(?:\.\d+)?)만원?', s)
    if m:
        return float(m.group(1))
    m = re.fullmatch(r'(\d+(?:\.\d+)?)', s)
    if m:
        return float(m.group(1))
    return None


NUM = r'(\d[\d,]*(?:\.\d+)?\s*(?:억(?:\s*\d[\d,]*\s*만?)?|천만원?|만원|만)?)'


def parse_price(text):
    dep = rent = None
    m = re.search(r'보증금\s*' + NUM + r'\s*원?\s*[/·,]?\s*월세\s*' + NUM, text)
    if m:
        dep, rent = _won10k(m.group(1)), _won10k(m.group(2))
    else:
        m = re.search(r'월세\s*' + NUM + r'\s*원?\s*[/·,]?\s*보증금\s*' + NUM, text)
        if m:
            rent, dep = _won10k(m.group(1)), _won10k(m.group(2))
        else:
            m = re.search(r'월세\s*(\d[\d,]*)\s*/\s*(\d[\d,]*)', text)     # '월세 500/45' = 보증금/월세 관행
            if m:
                dep, rent = _won10k(m.group(1)), _won10k(m.group(2))
    return dep, rent


def parse_maint(text):
    """반환: (금액 만원 또는 None, 상태 'AMOUNT'/'NONE'/'ACTUAL_COST'/'UNKNOWN')"""
    m = re.search(r'관리비\s*[:：]?\s*(없음|무)', text)
    if m:
        return 0.0, 'NONE'
    m = re.search(r'관리비\s*[:：]?\s*' + NUM, text)
    if m:
        v = _won10k(m.group(1))
        if v is not None:
            return v, 'AMOUNT'
    if re.search(r'관리비\s*[:：]?\s*(별도|실비|사용량)', text):
        return None, 'ACTUAL_COST'
    return None, 'UNKNOWN'


def _items_in(seg):
    found = []
    for it in ITEMS:
        if it in seg and not (it == '전기' and '공용전기' in seg and seg.count('전기') == seg.count('공용전기')):
            found.append(it)
    if '공용전기' in found and '전기' in found and seg.count('전기') == seg.count('공용전기'):
        found.remove('전기')
    return found


def parse_included(text):
    """'포함' 앞의 항목은 포함, '별도/불포함' 앞의 항목은 제외. 한 줄 안에서 구분자(, · / 와 괄호)로 분절."""
    inc, exc = [], []
    for line in text.split('\n'):
        if not re.search(r'포함|별도|불포함|제외', line):
            continue
        tail = line.split('관리비', 1)[-1]
        mc = re.search(r'(불포함|제외|별도|포함)\s*[:：]\s*(.*)', tail)
        if mc:                                        # '포함: 인터넷 · 가스(난방) · 공용전기' 형식
            lst = _items_in(re.sub(r'\([^)]*\)', '', mc.group(2)))
            (exc if mc.group(1) != '포함' else inc).extend(lst)
            continue
        for seg in re.split(r'[()（）/]', tail):
            seg = seg.strip()
            if not seg:
                continue
            m = re.search(r'(.*?)(불포함|제외|별도)', seg)
            if m and not re.search(r'포함', seg[: m.start(2)]):
                exc += _items_in(m.group(1))
                continue
            parts = re.split(r'(포함|불포함|별도|제외)', seg)
            cur = ''
            for p in parts:
                if p == '포함':
                    inc += _items_in(cur)
                    cur = ''
                elif p in ('별도', '불포함', '제외'):
                    exc += _items_in(cur)
                    cur = ''
                else:
                    cur += p
            # '전기는 각 호실 별도 청구' 처럼 별도가 뒤에 오는 경우는 위에서 처리됨
    return sorted(dict.fromkeys(inc)), sorted(dict.fromkeys(exc))


def parse_area(text):
    area, basis = None, None
    m = re.search(r'전용(?:면적)?\s*(\d+(?:\.\d+)?)\s*(?:㎡|m2|m²)', text)
    if m:
        area, basis = float(m.group(1)), '전용'
    else:
        m = re.search(r'(?:공급|계약)(?:면적)?\s*(\d+(?:\.\d+)?)\s*(?:㎡|m2|m²)', text)
        if m:
            area, basis = float(m.group(1)), '공급'
    return area, basis


def parse_floor(text):
    m = re.search(r'(반지하|지하\s*\d*층?|옥탑)', text)
    if m:
        return m.group(1)
    m = re.search(r'(\d+)\s*층', text)
    return m.group(1) if m else None


def parse_ad(text):
    dep, rent = parse_price(text)
    maint, mstate = parse_maint(text)
    inc, exc = parse_included(text)
    area, basis = parse_area(text)
    return dict(deposit_10k_krw=dep, rent_10k_krw=rent, maintenance_10k_krw=maint, maintenance_state=mstate,
                maintenance_included_items=inc, maintenance_excluded_items=exc, area_m2=area, area_basis=basis, floor=parse_floor(text))
