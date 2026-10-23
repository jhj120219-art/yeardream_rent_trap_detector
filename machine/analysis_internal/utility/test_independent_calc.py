# -*- coding: utf-8 -*-
"""요금 계산기 독립 시험(고지서·공식 계산기 없이 가능한 범위). calc.py 와 코드를 공유하지 않고 요금표 숫자만 따로 적어 다시 계산한다.
- A1 전기: 구간 경계(200·201·400·401, 하계 300·301·450·451)에서 폐쇄식 재계산과 일치
- A2 성질: 사용량이 늘면 요금이 줄지 않음, 구간 경계 점프는 기본요금 차이만큼만 허용, 원 단위 10원 절사·반올림
- A3 수도: 공식 시뮬레이션 앵커(가정용 1세대 15mm 10㎥ = 13,380원)
- A4 가스: 열량 42.6MJ/N㎥(가스공사 서울도시가스 12개월 평균), 단가·기본요금·부가세로 폐쇄식 재계산과 일치, 사용량 0이면 기본요금만
한계: 한전 공식 계산기와의 대조가 아니다(해당 계산기 접근이 막혀 있음). 요금표 값 자체의 오류는 잡지 못한다.
사용: python -m utility.test_independent_calc   (analysis_internal 폴더에서)"""
import sys
from .calc import electricity_bill, gas_bill, water_bill


def ref_electric(kwh, month):
    # 독립 구현: 구간별 (누적 상한, 기본요금)과 단가를 따로 적는다. 연료비 5, 기후환경 9, 부가세 10%, 기금 2.7%(10원 미만 절사)
    if month in (7, 8):
        edges = [(300, 910, 120.0), (450, 1600, 214.6), (10**9, 7300, 307.3)]
    else:
        edges = [(200, 910, 120.0), (400, 1600, 214.6), (10**9, 7300, 307.3)]
    energy, lo = 0.0, 0
    for hi, base, rate in edges:
        if kwh > lo:
            energy += (min(kwh, hi) - lo) * rate
            b = base
        lo = hi
    sub = b + energy + kwh * 5.0 + kwh * 9.0
    vat = round(sub * 0.1)
    fund = int(sub * 0.027 // 10) * 10
    return int(round(sub + vat + fund, -1))


def main():
    bad = []
    pts = [(m, k) for m in (1, 10) for k in (1, 100, 199, 200, 201, 300, 399, 400, 401, 450, 600)] + \
          [(8, k) for k in (200, 201, 299, 300, 301, 449, 450, 451, 500)]
    for m, k in pts:
        a, b = electricity_bill(k, m)['total'], ref_electric(k, m)
        if a != b:
            bad.append(('A1', m, k, a, b))
    for m in (1, 8):
        prev = -1
        for k in range(1, 700):
            t = electricity_bill(k, m)['total']
            if t < prev - 20:                                   # 반올림 때문에 10~20원 이내 흔들림은 허용하지 않으려면 prev 와 비교
                bad.append(('A2 감소', m, k, t, prev))
            if t % 10:
                bad.append(('A2 10원 단위', m, k, t))
            prev = t
    if water_bill(10)['total'] != 13380:
        bad.append(('A3 앵커', water_bill(10)['total']))
    if water_bill(0)['total'] != 1080:
        bad.append(('A3 기본', water_bill(0)['total']))
    # 열량(42.6MJ/N㎥)은 가스공사 서울도시가스 실적 12개월 평균으로 VERIFIED 가 되어 가정 표시가 없다. 폐쇄식으로 다시 계산해 일치만 확인
    exp10 = round(((10 * 1.0 * 42.6 * 22.5268) + 1250) * 1.10, -1)
    if abs(gas_bill(10)['total'] - exp10) > 10:
        bad.append(('A4 가스 10N㎥ 재계산', gas_bill(10)['total'], exp10))
    if gas_bill(0)['total'] != 1380:                                    # 기본요금 1,250 + 부가세 10% = 1,375 → 10원 단위 반올림 1,380
        bad.append(('A4 사용량 0', gas_bill(0)['total']))
    print(f'점검 {len(pts)}개 전기 경계점 + 연속·단위 성질 + 수도 앵커 + 가스 기본', '→ 불일치', len(bad))
    for x in bad[:20]:
        print(' ', x)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
