// State and response mapping retained from the original frontend, without local data.
import {emptyMaintenance,maintenanceItems,checkboxOptions} from './maintenance.mjs';
export const types={MULTI_UNIT:'다세대·연립',OFFICETEL:'오피스텔',DETACHED_MULTI:'단독·다가구',APARTMENT:'아파트'};
export const bases={EXCLUSIVE:'전용 면적',SUPPLY:'공급 면적',CONTRACT:'계약 면적',RENTAL_REPORTED:'신고 계약면적',UNKNOWN:'미확인'};
export const floors={UNKNOWN:'미확인',GROUND:'지상',BASEMENT:'지하'};
export const optionLabels={electricity_in_maintenance:'전기요금',water_in_maintenance:'수도요금',gas_in_maintenance:'가스요금',internet_status:'인터넷',elevator_status:'엘리베이터',parking_status:'주차'};
export const optionStates={UNKNOWN:'미확인',INCLUDED:'관리비에 포함',SEPARATE_CHARGE:'별도 납부',AVAILABLE:'이용 가능',NOT_AVAILABLE:'이용 불가'};
export const finite=v=>typeof v==='number'&&Number.isFinite(v);
export const number=v=>v===''||v==null?null:Number(v);
export const money=v=>finite(v)?v.toLocaleString('ko-KR',{maximumFractionDigits:2})+'만 원':'미제공';
export function initialState(){return{values:{district:'',dong:'',address:'',type:'',basis:'',area:'',deposit:'',rent:'',maintenance:'',year:'',floor:'',floorType:'UNKNOWN'},addressRegion:null,maintenanceItems:emptyMaintenance(),origins:{},confirmed:false,reviewRequired:false,sourceId:null,sourceOptions:{}};}
export function regionLabel(s,catalog){
 const d=catalog?.districts?.find(d=>d.district_code===s.values.district),dong=d?.dongs.find(x=>x.legal_dong_code===s.values.dong);
 if(d&&dong)return d.district_name+' '+dong.dong_name;
 const selected=s.addressRegion;
 return selected?.district_code===s.values.district&&selected?.legal_dong_code===s.values.dong&&selected.district_name&&selected.dong_name?selected.district_name+' '+selected.dong_name:'지역 확인 필요';
}
export function changeRegion(s,district,dong){const n=structuredClone(s);if(n.values.district===district&&n.values.dong===dong)return n;const hadRegion=Boolean(s.values.district&&s.values.dong);n.reviewRequired=s.reviewRequired||Boolean(hadRegion&&(s.values.area||s.values.rent||s.values.deposit));Object.assign(n.values,{district,dong,...(hadRegion?{address:''}:{})});n.addressRegion=null;n.confirmed=false;return n;}
export function applyAddress(s,address){const n=changeRegion(s,address.district_code||'',address.legal_dong_code||'');n.values.address=address.selected_address_text||address.road_address_text||address.address_text||'';n.addressRegion={district_code:n.values.district,legal_dong_code:n.values.dong,district_name:address.district_name||'',dong_name:address.dong||''};n.origins.address='주소 검색';n.confirmed=false;return n;}
export function applyDraft(s,response){
 const n=structuredClone(s),draft=response?.draft;
 if(!draft||!draft.source_extraction_id)throw new Error('이미지에서 매물 정보를 가져오지 못했습니다.');
 n.sourceId=draft.source_extraction_id;n.sourceOptions={};
 n.maintenanceItems=Object.fromEntries(maintenanceItems.map(({item,field})=>[item,draft.options?.[field]==='INCLUDED']));
 for(const key of Object.keys(optionLabels)){const value=draft.options?.[key];if(value==null)continue;const allowed=key.endsWith('_in_maintenance')?['UNKNOWN','INCLUDED','SEPARATE_CHARGE']:Object.keys(optionStates);n.sourceOptions[key]=allowed.includes(value)?value:'UNKNOWN';}
 const mapping={address_text:'address',building_type:'type',area_m2:'area',area_basis:'basis',deposit_10k_krw:'deposit',rent_10k_krw:'rent',built_year:'year',floor:'floor',floor_type:'floorType'};
 for(const [key,field] of Object.entries(mapping)){const value=draft.listing?.[key];if(value!=null){n.values[field]=String(value);n.origins[field]='사진 추출';}}
 if(draft.options?.maintenance_10k_krw!=null){n.values.maintenance=String(draft.options.maintenance_10k_krw);n.origins.maintenance='사진 추출';}
 if(!(n.values.type in types))n.values.type='';
 if(!(n.values.basis in bases))n.values.basis='UNKNOWN';
 if(!(n.values.floorType in floors))n.values.floorType='UNKNOWN';
 n.confirmed=false;return n;
}
export function validate(s,catalog){
 const v=s.values,issues=[],d=catalog?.districts?.find(d=>d.district_code===v.district);
 if(!d?.dongs.some(x=>x.legal_dong_code===v.dong))issues.push('비교할 시군구와 법정동을 선택해 주세요.');
 if(!(v.type in types))issues.push('주택 유형을 선택해 주세요.');if(!(v.basis in bases))issues.push('면적 기준을 선택해 주세요.');
 for(const [k,min,max,label] of [['area',5,200,'면적은 5~200㎡'],['deposit',0,Infinity,'보증금은 0 이상'],['rent',1,500,'월세는 1~500만 원']]){const val=number(v[k]);if(val===null||!Number.isFinite(val)||val<min||val>max)issues.push(label+'으로 입력해 주세요.');}
 if(v.maintenance!==''&&(!Number.isFinite(number(v.maintenance))||number(v.maintenance)<0))issues.push('관리비는 0 이상으로 입력해 주세요.');
 if(v.year!==''&&(!Number.isInteger(number(v.year))||number(v.year)<1950||number(v.year)>new Date().getFullYear()+1))issues.push('건축연도를 확인해 주세요.');
 if(v.floor!==''&&(!Number.isInteger(number(v.floor))||number(v.floor)===0))issues.push('층수는 0을 제외한 정수로 입력해 주세요.');
 if(v.floor!==''&&((number(v.floor)>0&&v.floorType==='BASEMENT')||(number(v.floor)<0&&v.floorType==='GROUND')))issues.push('층수와 지상·지하 구분을 확인해 주세요.');
 if(s.reviewRequired)issues.push('지역 변경 후 유지된 매물 조건을 다시 확인해 주세요.');
 if(!s.confirmed)issues.push('입력한 지역과 매물 조건 확인에 체크해 주세요.');
 return issues;
}
export function makePayload(s,catalog){
 const v=s.values,d=catalog.districts.find(x=>x.district_code===v.district),dong=d?.dongs.find(x=>x.legal_dong_code===v.dong);
 if(!dong)throw new Error('서버 목록에서 비교 지역을 선택해 주세요.');
 const knownFloor=v.floor!==''||v.floorType!=='UNKNOWN';
 const confirmedFields=[];if(s.confirmed&&v.floor!=='')confirmedFields.push('floor');if(s.confirmed&&v.floorType!=='UNKNOWN')confirmedFields.push('floor_type');
 return {schema_version:'1.1',listing:{district_code:d.district_code,legal_dong_code:dong.legal_dong_code,address_text:v.address||null,building_type:v.type,area_m2:number(v.area),area_basis:v.basis,deposit_10k_krw:number(v.deposit),rent_10k_krw:number(v.rent),built_year:number(v.year),floor:number(v.floor),floor_type:v.floorType||'UNKNOWN',floor_source:s.confirmed&&knownFloor?'USER_CONFIRMED':'UNKNOWN'},options:{...s.sourceOptions,...checkboxOptions(s),maintenance_10k_krw:number(v.maintenance)},confirmation:{user_confirmed:s.confirmed,input_source:s.sourceId?'IMAGE_REVIEWED':'ADDRESS_MANUAL',confirmed_fields:confirmedFields},...(s.sourceId?{source_extraction_id:s.sourceId}:{})};
}
export function reportView(report){
 const r=report?.rent?.result;if(!r||typeof r.status!=='string')throw new Error('서버 보고서 형식을 확인해야 합니다.');
 const p=r.prices_10k_krw||{},allowed=['COMPARED','REFERENCE_ONLY'].includes(r.status);
 return{result:r,status:r.status,median:allowed&&finite(p.median)?p.median:null,q25:allowed&&finite(p.q25)?p.q25:null,q75:allowed&&finite(p.q75)?p.q75:null,difference:allowed&&finite(r.rent_difference_10k_krw)?r.rent_difference_10k_krw:null,percent:allowed&&finite(r.rent_difference_pct)?r.rent_difference_pct*100:null,label:r.status==='COMPARED'?r.price_label:null,maintenance:finite(report.advertised_costs?.maintenance_10k_krw)?report.advertised_costs.maintenance_10k_krw:null};
}
export function comparisonRunner(client){let signature=null,task=null;return{run(payload,onStep,maintenanceScenario=null){const next=JSON.stringify({payload,maintenanceScenario});if(next!==signature){task=client.createComparison(payload,{maintenanceScenario});signature=next;}return task.run(onStep);},clear(){signature=null;task=null;}};}
