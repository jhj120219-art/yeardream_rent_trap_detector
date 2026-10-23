// Kakao Postcode: https://postcode.map.kakao.com/guide
const sdkUrl='https://t1.kakaocdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js';
let pending=null;
const constructor=()=>window.kakao?.Postcode||window.daum?.Postcode;

export function loadPostcode(){
 const ready=constructor();if(ready)return Promise.resolve(ready);
 if(pending)return pending;
 pending=new Promise((resolve,reject)=>{
  const script=document.createElement('script');script.src=sdkUrl;script.async=true;
  const fail=()=>{clearTimeout(timer);script.onload=script.onerror=null;script.remove();reject(new Error('카카오 주소검색을 불러오지 못했어요. 인터넷 연결을 확인한 뒤 다시 검색해 주세요.'));};
  const timer=setTimeout(fail,12000);
  script.onload=()=>{const Postcode=constructor();if(!Postcode){fail();return;}clearTimeout(timer);script.onload=script.onerror=null;resolve(Postcode);};
  script.onerror=fail;document.head.append(script);
 }).catch(e=>{pending=null;throw e;});
 return pending;
}

export function normalizePostcode(data){
 const text=v=>typeof v==='string'?v.trim():'';
 const district=text(data?.sigunguCode),dong=text(data?.bcode);
 const selected=data?.userSelectedType==='R'?text(data.roadAddress):data?.userSelectedType==='J'?text(data.jibunAddress):'';
 if(!selected||!/^\d{5}$/.test(district)||!/^\d{10}$/.test(dong)||!dong.startsWith(district))throw new Error('선택한 주소의 법정동 정보를 확인하지 못했어요. 정확한 도로명 또는 지번 주소를 다시 선택해 주세요.');
 return{selected_address_text:selected,address_text:text(data.jibunAddress),road_address_text:text(data.roadAddress),district_code:district,legal_dong_code:dong,district_name:[text(data.sido),text(data.sigungu)].filter(Boolean).join(' '),building_name:text(data.buildingName),postcode:text(data.zonecode),dong:[text(data.bname1),text(data.bname)].filter(Boolean).join(' ')};
}

export function isSupportedAddress(address,catalog){
 return Boolean(catalog?.districts?.find(d=>d.district_code===address?.district_code)?.dongs?.some(d=>d.legal_dong_code===address.legal_dong_code));
}
