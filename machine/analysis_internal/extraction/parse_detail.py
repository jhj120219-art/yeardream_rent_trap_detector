# -*- coding: utf-8 -*-
"""관리비 '상세보기' 창의 글자(OCR 또는 화면 텍스트) -> 구조화.
출력: total(원), mode(정액/실비/불명), undisclosed(세부내역 미고지), included(포함 항목 이름), amounts({항목: 원}), actual_items(항목별 '실비'로 적힌 항목),
      utility_included / utility_separate(수도·전기·가스·인터넷 중 포함 / 별도 실비), 값을 알 수 없으면 None.
규칙만 사용한다(소수점·금액 보정 없음). 모르는 표기는 불명으로 두고 확인을 요청한다."""
import re

UTIL = ['수도', '전기', '가스', '인터넷']
KNOWN = ['공용 관리비', '수도', '전기', '가스', '난방', '인터넷', 'TV', '청소', '기타 관리비']
LABELS = ['공용', '사용료', '전기', '수도', '가스', '난방', '인터넷', 'TV']


def parse_detail(text):
    t = re.sub(r'\s+', ' ', text)
    out = dict(total=None, mode='불명', undisclosed=False, included=[], amounts={}, actual_items=[], utility_included=[], utility_separate=[], notes=[])
    i = t.find('관리비 합계')
    if i < 0:
        out['notes'].append('관리비 합계 문구 없음')
        return out
    t = t[i:]
    m = re.search(r'관리비 합계\s*([\d,]+)\s*원', t)
    if m:
        out['total'] = int(m.group(1).replace(',', ''))
    if '세부내역 미고지' in t:
        out['undisclosed'] = True
    out['mode'] = '정액' if '정액관리비' in t else ('실비' if '실비' in t[:60] else '불명')
    m = re.search(r'포함 항목\s*[:;]?\s*(.*?)\s*(?:직전|최근|확인|$)', t)
    if m:                                       # 쉼표가 OCR 에서 사라질 수 있어 알려진 항목 이름을 직접 찾는다
        seg = m.group(1)
        out['included'] = [k for k in KNOWN if k in seg]
    body = t[:t.find('직전') if '직전' in t else (t.find('최근') if '최근' in t else len(t))]
    for lab in LABELS:
        m = re.search(r'(?<![가-힣])' + lab + r'\s*(?:([\d,]+)\s*원|(실비))', body)
        if m:
            if m.group(1):
                out['amounts'][lab] = int(m.group(1).replace(',', ''))
            else:
                out['actual_items'].append(lab)
    out['utility_included'] = [u for u in UTIL if u in out['included'] or u in out['amounts']]
    out['utility_separate'] = [u for u in UTIL if u in out['actual_items']]
    return out
