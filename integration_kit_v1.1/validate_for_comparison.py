"""입력 검증 예제 v1.1 (API 서버에서 호출, 설치 패키지 불필요). 분석 담당의 normalize_listing.py 와 같은 규칙.
실서비스에서는 normalize_listing.normalize_listing() 을 그대로 쓰는 것을 권장."""
VALID_AREA_BASIS = {"EXCLUSIVE", "SUPPLY", "CONTRACT", "RENTAL_REPORTED", "UNKNOWN"}
VALID_TYPES = {"APARTMENT", "OFFICETEL", "MULTI_UNIT", "DETACHED_MULTI", "SINGLE_MULTI_HOUSEHOLD"}


def validate_for_price_comparison(data: dict) -> dict:
    l = data.get("listing", data)
    conf = data.get("confirmation", {})
    issues = []
    confirmed = conf.get("user_confirmed") if "confirmation" in data else data.get("user_confirmed")
    if not confirmed:
        issues.append("USER_CONFIRMATION_REQUIRED")
    if l.get("building_type") not in VALID_TYPES:
        issues.append("BUILDING_TYPE_REVIEW_REQUIRED")
    if not l.get("district_code") or not (l.get("legal_dong_code") or l.get("dong") or l.get("legal_dong_name")):
        issues.append("ADDRESS_REVIEW_REQUIRED")
    for name in ("deposit_10k_krw", "rent_10k_krw"):
        v = l.get(name)
        if not isinstance(v, (int, float)) or v < 0 or (name == "rent_10k_krw" and v == 0):
            issues.append(name.upper() + "_REVIEW_REQUIRED")
    a = l.get("area_m2")
    if not isinstance(a, (int, float)) or a <= 0 or l.get("area_basis", "UNKNOWN") not in VALID_AREA_BASIS:
        issues.append("AREA_REVIEW_REQUIRED")
    # 면적 기준 때문에 입력을 일괄 차단하지 않는다(공급면적 입력은 분석 함수가 해당 매물만 가격 판정 보류).
    # floor == 0 은 미확인. 단독다가구의 층 유형은 사용자 확인(floor_source=USER_CONFIRMED)이 있어야 판정에 쓰인다(분석 함수가 처리).
    return {"status": "INPUT_REVIEW_REQUIRED" if issues else "READY_FOR_COMPARISON", "issues": sorted(set(issues))}


if __name__ == "__main__":
    import json
    from pathlib import Path
    sample = json.loads(Path(__file__).with_name("listing_confirmed_example.json").read_text(encoding="utf-8"))
    print(validate_for_price_comparison(sample))
