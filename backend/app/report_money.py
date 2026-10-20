"""Parse explicitly advertised monthly money without inferring missing values."""
import math


def advertised_money(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(',', '').replace('만원', '').strip())
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) and number >= 0 else None
