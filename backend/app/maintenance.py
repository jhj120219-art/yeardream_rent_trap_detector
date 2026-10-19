"""관리비 자료 대조. 월세 분석·시세 추정과 분리하며 출처의 진위를 인증하지 않는다."""
from datetime import date
import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from fastapi import HTTPException

CASES_PATH = Path(__file__).resolve().parents[1] / 'data' / 'maintenance_public_cases.json'


def load_public_cases():
    try:
        cases = json.loads(CASES_PATH.read_text(encoding='utf-8'))
        if not isinstance(cases, list) or len(cases) > 100:
            raise ValueError('invalid cases')
        for case in cases:
            Evidence.model_validate(case['evidence'])
        return {'items': cases, 'notice': '공개 광고에 적힌 관리비 사례입니다. 실제 청구액이나 지역 평균을 증명하는 자료가 아닙니다.'}
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, '공개 자료 사례가 연결되지 않았거나 형식이 잘못되었습니다.') from None


class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    source_type: Literal['ADVERTISEMENT', 'PUBLIC_NOTICE', 'MANAGER_STATEMENT', 'BILL']
    source_title: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl | None = None
    observed_on: date
    amount_10k_krw: float | None = Field(default=None, ge=0, le=100000, strict=True)
    period: Literal['MONTH', 'YEAR', 'UNKNOWN'] = 'UNKNOWN'
    basis: Literal['FIXED', 'ACTUAL', 'ESTIMATE', 'UNKNOWN'] = 'UNKNOWN'
    applies_to: Literal['SAME_UNIT', 'SAME_BUILDING', 'OTHER', 'UNKNOWN'] = 'UNKNOWN'
    user_confirmed: bool = Field(default=False, strict=True)
    billing_month: str | None = Field(default=None, pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    items: dict[Literal['COMMON', 'WATER', 'ELECTRICITY', 'GAS', 'INTERNET', 'TV', 'PARKING'], Literal['INCLUDED', 'EXCLUDED', 'UNKNOWN']] = Field(default_factory=dict)
    note: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def check_date(self):
        if self.observed_on > date.today():
            raise ValueError('확인 날짜는 미래일 수 없습니다.')
        return self


def compare(listing, evidence):
    quoted = listing['input'].get('options', {}).get('maintenance_10k_krw')
    reasons = []
    if not listing['input']['confirmation']['user_confirmed'] or not evidence['user_confirmed']:
        reasons.append('USER_CONFIRMATION_REQUIRED')
    if evidence['applies_to'] != 'SAME_UNIT':
        reasons.append('SAME_UNIT_NOT_CONFIRMED')
    if evidence['period'] != 'MONTH':
        reasons.append('MONTHLY_AMOUNT_REQUIRED')
    if quoted is None or evidence['amount_10k_krw'] is None:
        reasons.append('AMOUNT_UNKNOWN')
    comparable = not reasons
    delta = round(float(quoted) - evidence['amount_10k_krw'], 6) if comparable else None
    return {
        'status': ('AMOUNT_MATCH' if delta == 0 else 'AMOUNT_DIFFERENCE') if comparable else 'NEEDS_REVIEW',
        'quoted_monthly_10k_krw': quoted,
        'source_amount_10k_krw': evidence['amount_10k_krw'],
        'difference_10k_krw': delta,
        'reasons': reasons,
        'items': evidence['items'],
        'unknown_items': [k for k in ('COMMON','WATER','ELECTRICITY','GAS','INTERNET','TV','PARKING') if evidence['items'].get(k,'UNKNOWN') == 'UNKNOWN'],
        'source': evidence,
        'verification': 'USER_REVIEWED_SOURCE_UNVERIFIED',
        'notice': '입력 금액과 자료의 숫자 대조입니다. 포함 항목·사용량·청구 시기에 따라 달라질 수 있으며 적정 가격·실제 청구액·불법 여부를 판정하지 않습니다.',
    }
