# -*- coding: utf-8 -*-
"""관리비 '상세보기' 창의 글자(OCR 또는 화면 텍스트) -> 구조화. 다방(상세보기 팝업)과 직방(상세 화면 관리비 블록) 표기를 지원한다.
출력: total(원), mode(정액/혼합/실비/불명), undisclosed(세부내역 미고지), included(포함 항목 이름), excluded_items(미포함 항목), amounts({항목: 원}),
      actual_items(항목별 '실비'로 적힌 항목), not_provided(미제공·해당 없음), utility_included / utility_separate(수도·전기·가스·인터넷 중 포함 / 별도 실비·미포함),
      incomplete(읽은 항목이 서로 맞지 않아 확정하지 않는 사유 목록. 비어 있지 않으면 호출한 쪽은 '보류'로 다뤄야 한다).
원칙: 소수점·금액을 추정해 고치지 않는다. 항목 수·합계가 맞지 않으면 채우지 않고 incomplete 로 알린다(OCR 이 항목 이름을 빠뜨린 경우 등).
예외 1가지: 콤마 단위로 쓴 금액(총액·항목 금액)의 숫자 자리에 알파벳 o/O 가 있으면 0 으로 읽는다(OCR 문자 혼동)."""
import re

UTIL = ['수도', '전기', '가스', '인터넷']
KNOWN = ['공용 관리비', '일반(공용) 관리비', '수도', '전기', '가스', '난방', '인터넷', 'TV', '청소', '기타 관리비']
LABELS = ['공용', '사용료', '전기', '수도', '가스', '난방', '인터넷', 'TV']
SUB = ['전기', '수도', '가스', '난방', '인터넷', 'TV']                      # 사용료 하위 항목(화면 고정 순서)
END = r'(?=직전|최근|쇠근|$)'


def _num(s):
    return int(s.replace(',', '').replace('o', '0').replace('O', '0'))


def parse_detail(text):
    t = re.sub(r'\s+', ' ', text)
    out = dict(total=None, mode='불명', undisclosed=False, included=[], excluded_items=[], amounts={}, actual_items=[], not_provided=[],
               utility_included=[], utility_separate=[], incomplete=[], notes=[])
    i = t.find('관리비 합계')                                              # 다방: '관리비 합계 80,000 원 정액관리비 ...'
    zb = re.search(r'관리비\s*:?\s*(\d{1,3}(?:,[\dOo]{3})+|\d+)\s*원', t) if i < 0 else None   # 직방: '관리비 : 70,000원 일반(공용) 관리비 ...'
    if i < 0 and not zb:
        out['notes'].append('관리비 합계 문구 없음')
        return out
    if i >= 0:
        t = t[i:]
        m = re.search(r'관리비 합계\s*(\d{1,3}(?:,[\dOo]{3})+|\d+)\s*원', t)
    else:
        t = t[zb.start():]
        m = re.search(r'관리비\s*:?\s*(\d{1,3}(?:,[\dOo]{3})+|\d+)\s*원', t)
        out['notes'].append('직방 형식')
    if m:
        if re.search(r'[oO]', m.group(1)):
            out['notes'].append('총액 OCR o→0')
        out['total'] = _num(m.group(1))
    if '세부내역 미고지' in t or '고지하지 않아' in t:
        out['undisclosed'] = True
    out['mode'] = '정액' if '정액관리비' in t else ('혼합' if ('실비' in t and ('공용' in t)) else ('실비' if '실비' in t[:60] else '불명'))
    m = re.search(r'(?<!미)포함\s*[항함]목\s*[:;]?\s*(.*?)(?=미포함\s*[항함]목|' + END[3:], t)
    if m:                                        # 쉼표가 OCR 에서 사라질 수 있어 알려진 항목 이름을 직접 찾는다
        out['included'] = [k for k in KNOWN if k in m.group(1)]
    m = re.search(r'미포함\s*[항함]목\s*[:;]?\s*(.*?)' + END, t)
    if m:
        out['excluded_items'] = [k for k in KNOWN if k in m.group(1)]
    body = t[:min([x for x in (t.find('직전'), t.find('최근'), t.find('쇠근'), t.find('관리비 포함'), t.find('관리비 월')) if x >= 0] or [len(t)])]
    g = re.search(r'일반\(공용\)\s*관리비\s*(\d{1,3}(?:,[\dOo]{3})+|\d+)\s*원', body)           # 직방 공용 금액
    if g:
        out['amounts']['공용'] = _num(g.group(1))
        body = body.replace(g.group(0), ' ')
    g = re.search(r'기타 관리비\s*(\d{1,3}(?:,[\dOo]{3})+|\d+)\s*원', body)
    if g:
        out['amounts']['기타'] = _num(g.group(1))
    for lab in LABELS:
        m = re.search(r'(?<![가-힣])' + lab + r'\s*(?:(\d{1,3}(?:,[\dOo]{3})+|\d+)\s*원|(실비)|(미제공|해당 없음))', body)
        if m:
            if m.group(1):
                out['amounts'][lab] = _num(m.group(1))
            elif m.group(2):
                out['actual_items'].append(lab)
            else:
                out['not_provided'].append(lab)
    if re.search(r'사용료\s*(?:[\d,]+\s*원|실비|전기)', body):                    # 사용료 항목표가 있을 때만: 하위 항목이 모두 읽혔는지, 금액 합이 사용료와 맞는지 확인
        missing = [k for k in SUB if k not in out['amounts'] and k not in out['actual_items'] and k not in out['not_provided']]
        if missing:
            out['incomplete'].append('사용료 하위 항목 누락: ' + ','.join(missing))
        elif '사용료' in out['amounts'] and sum(out['amounts'].get(k, 0) for k in SUB) != out['amounts']['사용료']:
            out['incomplete'].append('사용료 하위 금액 합 불일치')
    am = out['amounts']
    if out['total'] is not None and '공용' in am:                            # 총액 = 공용 + 사용료(금액이 있으면) + 기타 — 맞지 않으면 항목이 빠졌을 수 있어 확정하지 않는다
        if am['공용'] + am.get('사용료', 0) + am.get('기타', 0) != out['total']:
            out['incomplete'].append('총액과 공용·사용료·기타 합 불일치')
    out['utility_included'] = [u for u in UTIL if u in out['included'] or u in out['amounts']]
    out['utility_separate'] = [u for u in UTIL if u in out['actual_items'] or u in out['excluded_items']]
    return out
