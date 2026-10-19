"""가격 계산은 루트의 기존 분석 모듈만 사용한다. 새 점수/가격 공식을 만들지 않는다."""
from pathlib import Path
import math
import numpy as np
import pandas as pd
import analyze
from normalize_listing import analyze_raw, normalize_listing


def json_safe(value):
    if isinstance(value, dict):
        return {k: json_safe(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value,np.generic):
        return json_safe(value.item())
    if isinstance(value,float) and not math.isfinite(value):
        return None
    return value


def load_pool(path: Path):
    # 'False' 문자열을 astype(bool)로 잘못 해석하지 않도록 CSV의 불리언을 먼저 검증한다.
    frame = pd.read_csv(path, dtype=str)
    needed={'date','CGG_CD','STDG_CD','gu','dong','usage','area','dep','rent','arch','is_new','basement','dup_suspect'}
    if not needed.issubset(frame.columns):
        raise ValueError("정제 CSV의 필수 열이 없습니다.")
    for col in ('is_new','basement','dup_suspect'):
        if not frame[col].isin(['True','False']).all():
            raise ValueError("정제 CSV의 불리언 값은 True/False여야 합니다.")
    for col in ('area','dep','rent'):
        nums=pd.to_numeric(frame[col],errors='coerce')
        if not np.isfinite(nums).all():
            raise ValueError("정제 CSV에 잘못된 숫자가 있습니다.")
        if ((nums < 0) if col == 'dep' else (nums <= 0)).any():
            raise ValueError("정제 CSV의 금액·면적 범위를 확인해 주세요.")
    for col in ('CGG_CD', 'STDG_CD'):
        if not frame[col].str.fullmatch(r'[0-9]{5}', na=False).all():
            raise ValueError("정제 CSV의 지역 코드는 5자리 문자열이어야 합니다.")
    for col in ('gu', 'dong', 'usage'):
        if frame[col].fillna('').str.strip().eq('').any():
            raise ValueError("정제 CSV의 지역·유형이 비어 있습니다.")
    arch = pd.to_numeric(frame['arch'], errors='coerce')
    if (frame['arch'].notna() & (~np.isfinite(arch) | (arch % 1 != 0))).any():
        raise ValueError("정제 CSV의 건축연도는 정수 또는 빈 값이어야 합니다.")
    if frame.empty or not (frame['is_new']=='True').any() or pd.to_datetime(frame['date'],errors='coerce').isna().any():
        raise ValueError("비교 가능한 신규 계약과 유효한 날짜가 필요합니다.")
    return analyze.load_pool(path)


def coverage(pool):
    """실제로 로드된 신규 계약의 지역·유형별 건수. 분석 가능성/정확도 보증 아님."""
    if pool is None:
        return []
    return [dict(gu=gu, usage=usage, basement=bool(basement), new_contract_count=len(arr['rent']))
            for (gu, usage, basement), arr in sorted(pool._g_gu.items())]


def review(raw):
    return normalize_listing(raw)


def run(raw, pool):
    # listing(options/confirmation 포함) 전체를 기존 어댑터에 넘긴다.
    return json_safe(analyze_raw(raw, pool))
