"""주소 후보만 제공. 사용자 선택 후 listing에 복사하며 호수/가격은 추정하지 않는다."""
import httpx
from fastapi import HTTPException


async def search_address(query,settings):
    if not settings.kakao_key:
        raise HTTPException(503,'주소 검색 API 설정이 필요합니다. 법정동과 매물정보는 직접 입력할 수 있습니다.')
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r=await client.get('https://dapi.kakao.com/v2/local/search/address.json',params={'query':query,'size':10},headers={'Authorization':'KakaoAK '+settings.kakao_key})
            r.raise_for_status()
        docs=r.json()['documents']
        if not isinstance(docs, list):
            raise ValueError('invalid documents')
        result=[]
        for doc in docs:
            addr=doc.get('address') or {}
            code=addr.get('b_code') or ''
            if len(code)!=10 or not code.isdigit():
                continue
            road=doc.get('road_address') or {}
            result.append({'address_text':addr.get('address_name'),'road_address_text':road.get('address_name'),'building_name':road.get('building_name'),'legal_dong_code':code,'district_code':code[:5],'dong':addr.get('region_3depth_name'),'requires_user_selection':True})
        return {'candidates':result,'source':'Kakao Local','note':'건물 주소 후보입니다. 호수·층·면적·금액은 별도로 확인해 주세요.'}
    except (httpx.HTTPError,ValueError,KeyError,TypeError,AttributeError):
        raise HTTPException(502,'주소 검색을 완료하지 못했습니다. 다시 시도하거나 직접 입력해 주세요.') from None
