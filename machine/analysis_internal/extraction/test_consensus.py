# -*- coding: utf-8 -*-
"""consensus.py 시험(합성 값). 사용: python test_consensus.py"""
from consensus import consensus, warnings_for

A = ('월세', 1000.0, 55.0, 19.83, 10.0)
B = ('월세', 500.0, 40.0, 23.14, 8.0)
B_BAD = ('월세', 1000.0, 40.0, 23.14, 8.0)      # 같은 카드(면적·관리비)를 다른 보증금으로 읽음
JEONSE = ('전세', 15000.0, None, 30.0, 12.0)


def by_status(res):
    d = {}
    for c in res:
        d.setdefault(c['status'], []).append(c)
    return d


def main():
    bad = []
    # 1) 두 엔진이 같게 읽은 카드만 extracted, 한 엔진만 읽은 카드는 값을 채우지 않는다
    res = by_status(consensus({'qwen': [A, B], 'paddle': [A], 'easy': [A, JEONSE]}))
    if [c['fields']['deposit_10k_krw']['value'] for c in res.get('extracted', [])] != [1000.0]:
        bad.append(('합의 카드', res.get('extracted')))
    held = res.get('on_hold', [])
    if len(held) != 2 or any(v['value'] is not None for c in held for v in c['fields'].values()):
        bad.append(('단독 읽기는 값을 채우지 않아야 함', held))
    # 2) 같은 카드에 금액이 엇갈리면 needs_review: 후보만 보여 주고 값은 비움
    res = by_status(consensus({'qwen': [B_BAD], 'paddle': [B]}))
    nr = res.get('needs_review', [])
    if len(nr) != 1 or len(nr[0]['candidates']) != 2 or nr[0]['fields']['deposit_10k_krw']['value'] is not None or 'extracted' in res:
        bad.append(('금액 불일치', res))
    # 3) 한 엔진이 합의된 카드와 같은 (면적·관리비)를 다르게 읽은 값은 합의 카드의 오독으로 보고 따로 보류 카드를 만들지 않는다
    res = by_status(consensus({'qwen': [B_BAD, B], 'paddle': [B], 'easy': [B]}))
    if len(res.get('extracted', [])) != 1 or 'needs_review' in res or 'on_hold' in res:
        bad.append(('합의 카드의 오독 처리', res))
    # 4) 단독 엔진 허용 금지, 사용자 확인은 이 모듈이 설정하지 않음
    try:
        consensus({'qwen': [A]}, min_agree=1)
        bad.append(('min_agree=1 허용됨',))
    except ValueError:
        pass
    if any(c['user_confirmed'] for c in consensus({'a': [A], 'b': [A]})):
        bad.append(('user_confirmed 가 켜짐',))
    # 5) 경고는 값을 바꾸지 않고 사유만 붙인다
    r = consensus({'a': [('월세', 5.0, 55.0, 19.83, 10.0)], 'b': [('월세', 5.0, 55.0, 19.83, 10.0)]})[0]
    if r['status'] != 'extracted' or 'DEPOSIT_UNDER_100_10K' not in r['warnings'] or r['fields']['deposit_10k_krw']['value'] != 5.0:
        bad.append(('경고', r))
    if warnings_for(*A):
        bad.append(('정상 값에 경고', warnings_for(*A)))
    # 6) 전세: 월세 칸은 비움
    r = consensus({'a': [JEONSE], 'b': [JEONSE]})[0]
    if r['fields']['rent_10k_krw']['value'] is not None or r['fields']['contract_type']['value'] != '전세':
        bad.append(('전세', r))
    print('실패 %d 건' % len(bad), *bad, sep='\n' if bad else ' ')
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
