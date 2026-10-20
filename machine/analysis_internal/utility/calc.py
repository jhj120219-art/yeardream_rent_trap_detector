# -*- coding: utf-8 -*-
"""사용량 -> 월 요금(원). 계산식은 각 공급자의 공식 설명을 따르며, 확인되지 않은 값은 tariffs.py 의 verified 표시를 확인할 것."""
from .tariffs import ELECTRIC, GAS, WATER


def electricity_bill(kwh: float, month: int) -> dict:
    E = ELECTRIC
    tiers = E['tiers_summer'] if month in E['summer_months'] else E['tiers_other']
    energy, prev, base = 0.0, 0.0, tiers[0][1]
    for cap, b, rate in tiers:
        top = kwh if cap is None else min(kwh, cap)
        if top > prev:
            energy += (top - prev) * rate
            base = b
        prev = top if cap is not None else prev
        if cap is None or kwh <= cap:
            break
    fuel = kwh * E['fuel_adjust_won_per_kwh']
    climate = kwh * E['climate_won_per_kwh']
    subtotal = base + energy + fuel + climate
    vat = round(subtotal * E['vat_rate'])
    fund = int(subtotal * E['fund_rate'] // 10 * 10)
    total = int(round(subtotal + vat + fund, -1))
    return dict(total=total, base=base, energy=round(energy), fuel=round(fuel), climate=round(climate), vat=vat, fund=fund,
                assumptions=[k for k, v in E['verified'].items() if not v])


def gas_bill(nm3: float) -> dict:
    G = GAS
    mj = nm3 * G['correction'] * G['mj_per_nm3']
    use = mj * G['won_per_mj']
    subtotal = use + G['base_won_per_month']
    total = int(round(subtotal * (1 + G['vat_rate']), -1))
    return dict(total=total, use=round(use), base=G['base_won_per_month'], assumptions=[k for k, v in G['verified'].items() if not v])


def water_bill(m3: float) -> dict:
    W = WATER
    total = W['base_won_per_month_15mm'] + m3 * (W['waterworks_won_per_m3'] + W['sewerage_won_per_m3'] + W['water_use_charge_won_per_m3'])
    return dict(total=int(total // 10 * 10), assumptions=[])
