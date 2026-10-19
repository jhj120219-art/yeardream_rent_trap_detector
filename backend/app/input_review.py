"""저장된 이미지 추출로 확인용 폼을 만든다. 자동 등록·분석은 하지 않는다."""
LISTING_FIELDS = {'address_text','building_type','area_m2','area_basis','deposit_10k_krw',
                  'rent_10k_krw','floor','total_floors','built_year','floor_type','floor_source'}
OPTION_FIELDS = {'maintenance_10k_krw','internet_status','elevator_status','parking_status',
                 'electricity_in_maintenance','gas_in_maintenance','water_in_maintenance'}


def listing_draft(source):
    result=source['result']
    usable=result.get('extraction_status')=='EXTRACTED_NEEDS_REVIEW'
    fields=result.get('fields',{})
    def value(key):
        field=fields.get(key,{})
        return field.get('value') if usable and field.get('raw_text') else None
    listing={key:value(key) for key in sorted(LISTING_FIELDS)}
    listing.update(district_code=None,legal_dong_code=None,unit_ho=None,as_of=None,
                   floor_source='IMAGE_EXTRACTED')
    options={key:value(key) for key in sorted(OPTION_FIELDS)}
    missing=[k for k in ('district_code','legal_dong_code','building_type','area_m2',
                         'area_basis','deposit_10k_krw','rent_10k_krw','as_of')
             if listing.get(k) in (None,'UNKNOWN')]
    return {'draft':{'schema_version':'1.1','listing':listing,'options':options,
                      'confirmation':{'user_confirmed':False,'confirmed_fields':[],
                                      'input_source':'IMAGE_REVIEWED'},
                      'source_extraction_id':source['id']},
            'extraction_status':result.get('extraction_status'),
            'missing_or_unknown_fields':missing,'source_fields':fields,
            'notice':'확인용 입력 후보입니다. 값을 확인·수정한 뒤 등록해 주세요. 주소 코드·호수는 추정하지 않습니다.'}
