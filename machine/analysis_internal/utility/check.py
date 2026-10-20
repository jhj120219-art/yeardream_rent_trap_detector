# -*- coding: utf-8 -*-
"""관리비 점검 로직 초안(임시). 정상/과다를 확정하지 않고 REFERENCE_ONLY / REVIEW_REQUIRED / INSUFFICIENT_DATA 만 낸다.
원칙: (1) 관리비 총액에서 추정 공과금 합계를 뺀 값을 '부당/설명 안 되는 금액'으로 해석하지 않는다. (2) 항목별 금액이 있을 때만 해당 항목을 비교한다.
(3) 결과표 평균은 분포가 아니므로 '관점별 참고 범위'로만 쓰고, 가스는 사용 여부·난방 방식 미확인이면 보류한다. (4) 시세 엔진 라벨에는 영향을 주지 않는다."""
from . import reference as R

ITEMS = {'water': '수도', 'electric': '전기', 'gas': '가스', 'internet': '인터넷'}
INTERNET_RANGE = (17600, 30000)       # KT 인터넷 요금제 공개가(월, VAT 포함) 예시 범위. 통신사·약정별로 다름(참고만)
REVIEW_FACTOR = 1.5                   # 항목별 청구액이 참고 범위 상한의 1.5배를 넘으면 '추가 확인 필요'. 임시값이며 실제 고지서 평가셋으로 정해야 함


def _range(item, month, household):
    if item == 'internet':
        return INTERNET_RANGE
    key = {'water': 'water', 'electric': 'electricity', 'gas': 'gas'}[item]
    vals = []
    views = [('housing', '다세대/연립/기타'), ('size', f'{min(household, 4)}명' if household < 4 else '4명이상'), ('area', '33㎡미만')]
    if item == 'gas':
        views.append(('heating', '도시가스'))      # 도시가스 난방 가구 평균(서울 723.7N㎥/년, 표본 917가구). 전체 평균(651.4)에는 가스 미사용 가구가 섞여 있음
    for view, cat in views:
        vals.append(R.estimate(view, cat, month, household)[key]['bill'])
    return min(vals), max(vals)


def assess(*, month: int, household: int = 1, included=(), itemized=None, mgmt_total=None, gas_user=None, heating=None) -> dict:
    itemized = itemized or {}
    included = set(included) | set(itemized)
    out = dict(status='INSUFFICIENT_DATA', items={}, notes=[], never=['총액-추정합계를 부당 청구액으로 해석하지 않음'])
    if not included:
        out['notes'].append('관리비에 어떤 항목이 포함되는지 알 수 없어 비교하지 않습니다. 포함 항목과 항목별 금액을 확인해 주세요.')
        return out
    review = False
    for it in sorted(included):
        if it not in ITEMS:
            continue
        info = dict(name=ITEMS[it])
        if it == 'gas' and (gas_user is not True or heating != '개별가스'):
            info.update(state='HOLD', reason='가스 사용 여부·난방 방식(개별 도시가스) 미확인이라 참고 비용을 내지 않습니다.')
            out['items'][it] = info
            continue
        lo, hi = _range(it, month, household)
        info.update(reference_low=lo, reference_high=hi, basis='서울 결과표 관점별 참고 범위(분포 아님, 2023 사용량×2026 요율)')
        amt = itemized.get(it)
        if amt is None:
            info.update(state='REFERENCE_ONLY', reason='항목별 금액이 없어 비교하지 않고 참고 범위만 보여줍니다.')
        elif amt > hi * REVIEW_FACTOR:
            info.update(state='REVIEW_REQUIRED', amount=amt, reason=f'청구 {amt:,}원이 참고 범위 상한({hi:,}원)의 {REVIEW_FACTOR}배를 넘어 사용량·계량 방식·청구 내역 확인이 필요합니다.')
            review = True
        else:
            info.update(state='REFERENCE_ONLY', amount=amt, reason='참고 범위를 크게 벗어나지 않았습니다(정상 판정이 아님).')
        out['items'][it] = info
    states = {v['state'] for v in out['items'].values()}
    if review:
        out['status'] = 'REVIEW_REQUIRED'
    elif 'REFERENCE_ONLY' in states:
        out['status'] = 'REFERENCE_ONLY'
    if mgmt_total is not None:
        out['notes'].append('관리비 총액은 청소·공용전기·승강기 등 공용 항목을 포함할 수 있어 추정 공과금과의 차액을 설명되지 않는 금액으로 보지 않습니다.')
    return out
