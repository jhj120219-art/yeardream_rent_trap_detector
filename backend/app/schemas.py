from datetime import date
import json
import math
import re
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class Confirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_confirmed: StrictBool = False
    confirmed_fields: list[str] = Field(default_factory=list, max_length=100)
    input_source: Literal["ADDRESS_MANUAL", "IMAGE_REVIEWED"] = "ADDRESS_MANUAL"


class ListingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.1"] = "1.1"
    listing: dict[str, Any]
    options: dict[str, Any] = Field(default_factory=dict)
    confirmation: Confirmation = Field(default_factory=Confirmation)
    source_extraction_id: str | None = Field(default=None, min_length=1, max_length=64)
    previous_listing_id: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("listing", "options")
    @classmethod
    def validate_values(cls, value):
        if len(json.dumps(value, ensure_ascii=False)) > 16000:
            raise ValueError("입력 항목이 너무 큽니다.")
        for key, item in value.items():
            numeric = key in {"area_m2", "deposit_10k_krw", "rent_10k_krw", "built_year", "floor", "total_floors", "maintenance_10k_krw"}
            if numeric and isinstance(item, bool):
                raise ValueError("숫자 항목에 불리언을 사용할 수 없습니다.")
            if key in {"district_code", "legal_dong_code"} and item is not None:
                length = 5 if key == 'district_code' else 10
                if not isinstance(item, str) or not re.fullmatch(r'[0-9]{%d}' % length, item):
                    raise ValueError("주소 코드는 지정 길이의 숫자 문자열이어야 합니다.")
            if not isinstance(item, (str,int,float,bool,type(None))):
                raise ValueError("각 항목에는 문자열·숫자·불리언·null만 사용할 수 있습니다.")
            if isinstance(item,float) and not math.isfinite(item):
                raise ValueError("유한한 숫자만 입력해 주세요.")
            if isinstance(item,str) and len(item)>1000:
                raise ValueError("항목 길이는 1000자 이하여야 합니다.")
            if key in {"area_m2","deposit_10k_krw","rent_10k_krw","built_year","floor","total_floors","maintenance_10k_krw"} and isinstance(item,str):
                # 기존 정규화가 받는 쉼표/만원 표기는 유지하되 NaN/Infinity는 차단한다.
                try:
                    n=float(item.replace(',','').replace('만원','').replace('㎡','').strip())
                except ValueError:
                    pass  # 숫자로 읽을 수 없는 값은 기존 정규화가 확인 필요로 반환한다.
                else:
                    if not math.isfinite(n):
                        raise ValueError("유한한 숫자만 입력해 주세요.")
            if key in {'built_year', 'floor', 'total_floors'} and item is not None:
                try:
                    number = float(item)
                except (TypeError, ValueError):
                    raise ValueError("연도와 층은 정수 또는 null이어야 합니다.") from None
                if not number.is_integer():
                    raise ValueError("연도와 층은 소수 부분이 없는 정수여야 합니다.")
                if key == 'built_year' and not 1950 <= number <= date.today().year + 1:
                    raise ValueError("건축연도를 확인해 주세요.")
                if key == 'total_floors' and number < 1:
                    raise ValueError("건물 전체 층수는 1 이상이어야 합니다.")
            if key == 'maintenance_10k_krw' and item is not None:
                try:
                    number = float(str(item).replace(',', '').replace('만원', '').strip())
                except ValueError:
                    raise ValueError("관리비는 0 이상의 숫자 또는 null이어야 합니다.") from None
                if not math.isfinite(number) or number < 0:
                    raise ValueError("관리비는 0 이상의 숫자 또는 null이어야 합니다.")
        district, legal = value.get('district_code'), value.get('legal_dong_code')
        for key in ('main_no','sub_no'):
            if value.get(key) is not None and (not isinstance(value[key],str) or not re.fullmatch(r'[0-9]{1,4}',value[key])):
                raise ValueError('지번 본번·부번은 1~4자리 숫자 문자열 또는 null이어야 합니다.')
        if value.get('main_no') is not None and int(value['main_no'])==0:
            raise ValueError('지번 본번은 1 이상이어야 합니다.')
        if value.get('sub_no') is not None and value.get('main_no') is None:
            raise ValueError('지번 부번을 입력할 때는 본번도 필요합니다.')
        if district and legal and not legal.startswith(district):
            raise ValueError("법정동 코드와 자치구 코드가 일치하지 않습니다.")
        floor, total = value.get('floor'), value.get('total_floors')
        if floor is not None and total is not None and float(floor) > float(total):
            raise ValueError("매물 층이 건물 전체 층수보다 큽니다.")
        floor_type = value.get('floor_type')
        if floor is not None and ((float(floor) > 0 and floor_type == 'BASEMENT') or (float(floor) < 0 and floor_type == 'GROUND')):
            raise ValueError("매물 층과 지상·지하 구분을 확인해 주세요.")
        if value.get('as_of') is not None:
            parsed=date.fromisoformat(str(value['as_of']))
            if not 1950 <= parsed.year <= 2100:
                raise ValueError('비교 기준일은 1950~2100년 사이로 입력해 주세요.')
        return value
