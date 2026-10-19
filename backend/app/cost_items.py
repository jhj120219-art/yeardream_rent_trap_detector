"""광고에서 확인한 포함 항목만 선별. 근거 없는 평균 금액은 넣지 않는다."""
def cost_items(options, confirmed):
    fields={'ELECTRICITY':'electricity_in_maintenance','GAS':'gas_in_maintenance',
            'WATER':'water_in_maintenance','INTERNET':'internet_status'}
    items=[]
    for item,field in fields.items():
        stated=options.get(field)
        status=stated if stated in ('INCLUDED','SEPARATE_CHARGE') else 'UNKNOWN'
        items.append({
            'item':item,'advertised_status':status,'source_field':field,
            'confirmed':confirmed,
            'additional_to_maintenance_10k_krw':0 if confirmed and status=='INCLUDED' else None,
            'reference_monthly_10k_krw':None,
            'reference_state':'NO_MATCHED_REFERENCE',
            'action':('INCLUDED_DO_NOT_ADD' if status=='INCLUDED' else
                      'REFERENCE_REQUIRED' if status=='SEPARATE_CHARGE' else 'INCLUSION_UNKNOWN')
                      if confirmed else 'REVIEW_ADVERTISEMENT',
        })
    return {'items':items,
            'reference_requirements':['지역','주택 유형','전용면적','기준 월/계절','가구원 수','난방 방식','출처·표본 수·금액 단위'],
            'notice':'포함 항목은 추가 요금에 중복 합산하지 않습니다. 포함된 실제 사용료가 0원이라는 뜻은 아닙니다. 참고 평균 자료는 아직 연결하지 않았습니다.'}
