"""Meeting-approved identity and cost display policy; no price estimation rules."""

SERVICE_NAME = '월세구멍'
SLOGAN = '마음에 든 집, 놓친 건 없을까?'


def public_identity():
    return {
        'name': SERVICE_NAME,
        'slogan': SLOGAN,
        'maintenance_policy': 'FIVE_ITEMS_ALL_HOUSING_TYPES',
        'maintenance_input_mode': 'CHECKBOX_TOTAL_V1',
        'maintenance_display_items': [
            {'item': 'WATER', 'label': '수도세'},
            {'item': 'ELECTRICITY', 'label': '전기세'},
            {'item': 'GAS', 'label': '가스비'},
            {'item': 'INTERNET', 'label': '인터넷'},
            {'item': 'OTHER', 'label': '기타 관리비'},
        ],
        'notice': '모든 주택 유형에 동일한 5항목을 사용합니다. 청소·공용은 기타의 설명으로 보존합니다. 자료 지원 범위와 계산 가능 여부는 별도로 확인합니다.',
    }
