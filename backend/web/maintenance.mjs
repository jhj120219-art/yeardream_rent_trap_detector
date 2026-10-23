// CHECKBOX_TOTAL_V1, backend main 8e602b6 (2026-10-22).
export const maintenanceItems=[
 {item:'WATER',label:'수도',field:'water_in_maintenance'},
 {item:'ELECTRICITY',label:'전기',field:'electricity_in_maintenance'},
 {item:'GAS',label:'가스',field:'gas_in_maintenance'},
 {item:'INTERNET',label:'인터넷',field:'internet_status'},
 {item:'OTHER',label:'기타',field:'other_in_maintenance'},
];
export const emptyMaintenance=()=>Object.fromEntries(maintenanceItems.map(({item})=>[item,false]));
export const checkboxOptions=s=>Object.fromEntries([['maintenance_input_mode','CHECKBOX_TOTAL_V1'],...maintenanceItems.map(({item,field})=>[field,s.maintenanceItems?.[item]===true?'INCLUDED':'UNKNOWN'])]);
export const won=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0?value.toLocaleString('ko-KR',{maximumFractionDigits:1})+'원':'자료 없음';

export function referenceScenario(s,capabilities,month=new Date().getMonth()+1){
 if(!s.confirmed||!maintenanceItems.some(({item})=>s.maintenanceItems?.[item])||!s.values.district.startsWith('11')||capabilities.maintenance_enabled!==true||capabilities.machine_maintenance_enabled!==true)return null;
 return{target_month:month,household_size:null,heating_type:'모름',gas_user:'모름',metering:'UNKNOWN',acknowledge_reference_limits:true};
}

export function maintenanceView(report,s){
 const groups=report?.maintenance_reference_groups;
 const selected=groups?.selected;
 const connected=groups?.version==='CHECKBOX_TOTAL_V1'&&['AVAILABLE','PARTIAL_REFERENCE'].includes(groups?.state);
 const rows=Array.isArray(selected?.items)?selected.items:[];
 const items=maintenanceItems.filter(({item})=>s.maintenanceItems?.[item]===true).map(({item,label})=>{
  const matches=rows.filter(r=>r.item===item),row=matches.length===1?matches[0]:null;
  const low=row?.reference_low_krw,high=row?.reference_high_krw,mid=row?.reference_midpoint_krw;
  const valid=connected&&row?.selected===true&&row?.reference_state==='AVAILABLE'&&typeof row?.source==='string'&&row.source.trim()&&Number.isSafeInteger(low)&&Number.isSafeInteger(high)&&0<=low&&low<=high&&typeof mid==='number'&&Number.isFinite(mid)&&mid===(low+high)/2;
  return{item,label,amount:valid?mid:null,low:valid?low:null,high:valid?high:null,source:valid?row.source:null};
 });
 const complete=items.length>0&&items.every(row=>row.amount!==null);
 const total=complete&&selected?.state==='AVAILABLE'&&selected.reference_midpoint_total_krw===items.reduce((sum,row)=>sum+row.amount,0)?selected.reference_midpoint_total_krw:null;
 return{items,total,missing:items.filter(row=>row.amount===null).map(row=>row.label),connected};
}
