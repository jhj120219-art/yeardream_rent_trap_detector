# -*- coding: utf-8 -*-
"""목록 카드 읽기 합의 — 여러 엔진(Qwen2-VL · EasyOCR · PaddleOCR 등)이 읽은 카드 값 중 **둘 이상이 같게 읽은 값만** 자동 입력 후보로 올린다.
나머지는 값을 채우지 않는다: 한 엔진만 읽었으면 on_hold, 같은 면적·관리비 카드에 서로 다른 금액이 읽혔으면 needs_review(후보만 보여 줌).
이유: 개발에 쓰지 않은 46카드에서 Qwen 단독은 읽은 55건 중 22건이 틀렸고 값만 보는 범위 검사로는 7건만 잡혔다(그럴듯한 값이 다른 카드와 섞임).
다수결은 틀린 카드 0개(완전 정답 32/46, 나머지는 보류)였다. 이 모듈은 값을 고치거나 추측하지 않는다. 엔진 실행(OCR 호출)은 여기에 없다.

입력: engine_reads = {엔진이름: [(종류, 보증금_만원, 월세_만원 또는 None, 면적_㎡, 관리비_만원), ...]}  (종류는 '월세'|'전세')
출력: 3번 머신(광고 이미지 추출) 공통 형식의 카드별 dict. 상태: extracted(합의됨, 사용자 확인 전 초안) / needs_review / on_hold.
어떤 상태든 사용자가 확인하기 전에는 월세 비교·관리비 추정에 넘기지 않는다(`user_confirmed` 는 이 모듈이 설정하지 않는다).
"""

SCHEMA_VERSION = '1.0'
MACHINE = 'listing_extractor'


def warnings_for(kind, deposit, rent, area, maint):
    """값만 보는 경고(오류 탐지용). 값을 바꾸거나 거르지 않고 사유만 붙인다."""
    w = []
    if kind == '월세':
        if deposit < 100:
            w.append('DEPOSIT_UNDER_100_10K')
        if rent is None:
            w.append('RENT_MISSING')
        else:
            if rent < 10:
                w.append('RENT_UNDER_10_10K')
            if rent >= 150:
                w.append('RENT_150_10K_OR_MORE')
            if deposit < rent:
                w.append('DEPOSIT_LESS_THAN_RENT')
    if area > 100:
        w.append('AREA_OVER_100_M2')
    if maint >= 30:
        w.append('MAINTENANCE_30_10K_OR_MORE')
    return w


def _card(status, read=None, engines=(), candidates=None, reason=None):
    fields = {k: {'value': None, 'status': 'not_read'} for k in ('contract_type', 'deposit_10k_krw', 'rent_10k_krw', 'area_m2', 'maintenance_10k_krw')}
    warnings = []
    if status == 'extracted' and read is not None:
        kind, dep, rent, area, maint = read
        vals = {'contract_type': kind, 'deposit_10k_krw': dep, 'rent_10k_krw': rent, 'area_m2': area, 'maintenance_10k_krw': maint}
        warnings = warnings_for(*read)
        for k, v in vals.items():
            fields[k] = {'value': v, 'status': 'extracted'} if v is not None else {'value': None, 'status': 'not_read'}
    return {'schema_version': SCHEMA_VERSION, 'machine': MACHINE, 'status': status, 'fields': fields,
            'agreement': {'engines': sorted(engines), 'min_agree': None},
            'candidates': candidates or [], 'warnings': warnings, 'reason': reason, 'user_confirmed': False}


def consensus(engine_reads, min_agree=2):
    """카드별 결과 리스트를 돌려준다. 같은 읽기를 min_agree 개 이상 엔진이 냈을 때만 extracted."""
    if min_agree < 2:
        raise ValueError('min_agree 는 2 이상이어야 한다(단독 엔진 값은 자동 입력하지 않는다)')
    who = {}
    for eng, reads in engine_reads.items():
        for r in {tuple(x) for x in reads}:
            who.setdefault(r, set()).add(eng)
    agreed = {r for r, e in who.items() if len(e) >= min_agree}
    out = []
    for r in sorted(agreed, key=repr):
        c = _card('extracted', r, who[r])
        c['agreement']['min_agree'] = min_agree
        out.append(c)
    # 합의되지 못한 읽기: 같은 (면적, 관리비) 카드에 서로 다른 금액이 있으면 needs_review, 하나뿐이면 on_hold
    rest = {}
    for r, e in who.items():
        if r not in agreed and not any((a[3], a[4]) == (r[3], r[4]) for a in agreed):
            rest.setdefault((r[3], r[4]), []).append(r)
    for key, rs in sorted(rest.items(), key=repr):
        engines = set().union(*(who[r] for r in rs))
        if len(rs) > 1:
            cands = [dict(zip(('contract_type', 'deposit_10k_krw', 'rent_10k_krw', 'area_m2', 'maintenance_10k_krw'), r), engines=sorted(who[r])) for r in sorted(rs, key=repr)]
            out.append(_card('needs_review', engines=engines, candidates=cands, reason='ENGINES_DISAGREE_ON_AMOUNTS'))
        else:
            out.append(_card('on_hold', engines=engines, reason='SINGLE_ENGINE_READ_NOT_AUTOFILLED'))
    return out
