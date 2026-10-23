import localCatalog from './location-catalog.mjs';
import {createRentClient} from './rent-client.mjs';
import {loadPostcode,normalizePostcode,isSupportedAddress} from './postcode.mjs';
import {maintenanceItems,maintenanceView,referenceScenario,won} from './maintenance.mjs';
import {initialState,types,bases,floors,optionLabels,optionStates,finite,number,money,regionLabel,applyAddress,applyDraft,changeRegion,validate,makePayload,reportView,comparisonRunner} from './model.mjs';

const $=id=>document.getElementById(id);
const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let api=null,runner=null,catalog={districts:[]},capabilities={},connected=false,busy=false;
let state=initialState(),screen='start',mode='capture',addressBack='start',candidates=[],chosenAddress=null;
let file=null,fileUrl=null,extractionJob=null,connectionSignature='';
let postcodeRequest=0,postcodeTimer=null;
const setText=(id,text)=>{$(id).textContent=text;};
function progress(text){setText('progress',text);$('progress').hidden=!text;}
function error(text){setText('action-error',text);$('action-error').hidden=!text;}
function failure(e){
 const messages={401:'접속키 또는 세션이 유효하지 않아요. 연결을 초기화한 뒤 다시 연결해 주세요.',403:'접근 권한을 확인해 주세요.',404:'요청한 자료를 찾지 못했어요.',409:'입력 충돌이 발생했어요. 조건을 확인한 뒤 다시 요청해 주세요.',413:'이미지는 8MB 이하로 올려 주세요.',415:'PNG·JPG·WebP 이미지를 선택해 주세요.',422:'입력한 값과 면적 기준을 다시 확인해 주세요.',429:'요청이 많아요. 잠시 후 다시 시도해 주세요.',502:'연결된 서비스가 응답하지 않아요. 잠시 후 다시 시도해 주세요.',504:'이미지 판독 제한 시간(4분)을 초과했어요. 지도·메뉴를 제외하고 매물 목록 영역만 작게 잘라 다시 올려 주세요. 진단: OCR_TIMEOUT',503:'서버의 데이터 또는 기능이 준비되지 않았어요.'};
 const message=messages[e.status]||(e.code==='TIMEOUT'?'응답 시간이 초과됐어요. 입력을 유지하고 다시 시도해 주세요.':e.code==='NETWORK_OR_RESPONSE_ERROR'?'서버 응답을 받지 못했어요. 서버 주소와 연결 상태를 확인해 주세요.':e.message||'요청을 완료하지 못했어요.');
 return message+(e.requestId?'\n요청 ID: '+e.requestId:'');
}
function lock(value){busy=value;$('content').inert=value;$('connection-form').inert=value;document.querySelector('.steps').setAttribute('aria-busy',String(value));}
function show(name){screen=name;document.querySelectorAll('[data-screen]').forEach(el=>el.hidden=el.dataset.screen!==name);const step={start:0,collect:1,fill:2,result:3}[name];document.querySelectorAll('.steps li').forEach((el,i)=>{if(i===step)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');});error('');progress('');window.scrollTo({top:0,behavior:'instant'});if(name!=='start')document.querySelector(`[data-screen="${name}"] h2`)?.focus({preventScroll:true});}
function requireConnection(){if(connected)return true;$('connection-settings').open=true;setText('connection-status','서버 주소와 접속키를 입력해 연결해 주세요.');$('server-url').focus();return false;}
function invalidate(){state.confirmed=false;$('confirmed').checked=false;$('validation').hidden=true;}
function selectMode(next){if(next!=='address')closeAddressSearch();mode=next;for(const name of ['capture','address']){const on=name===next;$('choose-'+name).setAttribute('aria-selected',String(on));$('choose-'+name).tabIndex=on?0:-1;$(name+'-panel').hidden=!on;}error('');}
for(const name of ['capture','address']){
 $('choose-'+name).onclick=()=>selectMode(name);
 $('choose-'+name).onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const target=e.key==='Home'?'capture':e.key==='End'?'address':name==='capture'?'address':'capture';selectMode(target);$('choose-'+target).focus();}};
}
function updateCapabilities(){
 $('local-ocr-options').hidden=!connected||capabilities.image_provider!=='LOCAL_OCR';
 const imageUnavailable=connected&&!capabilities.vision_configured;
 $('extract').disabled=imageUnavailable;
 $('capture-note').hidden=!imageUnavailable;setText('capture-note',imageUnavailable?'현재 서버에서 이미지 인식을 사용할 수 없어요. 직접 조건을 입력해 주세요.':'');
 renderAddresses();
 if(connected){setText('coverage-region',catalog.districts.map(d=>d.district_name).join(' · '));const usage=[...new Set((capabilities.loaded_coverage||[]).map(c=>c.usage).filter(Boolean))];if(usage.length)setText('coverage-types',usage.join(' · '));}
}
$('connection-form').onsubmit=async e=>{
 e.preventDefault();if(busy||connected)return;
 if(location.protocol==='file:'){setText('connection-status','start.cmd를 실행한 뒤 http://localhost:5173에서 열어 주세요.');return;}
 const url=$('server-url').value.trim(),key=$('team-key').value.trim();if(!url){setText('connection-status','서버 주소를 입력해 주세요.');return;}
 lock(true);setText('connection-status','서버에 연결하고 있어요.');
 try{const signature=url+'\n'+key;if(signature!==connectionSignature){api=createRentClient({baseUrl:url,teamKey:key});connectionSignature=signature;}
  const started=await api.start();if(started.capabilities.data_status!=='READY')throw new Error('서버의 분석 데이터가 준비되지 않았어요.');
  if(!Array.isArray(started.locations?.districts)||!started.locations.districts.length)throw new Error('지원 지역 목록을 불러오지 못했어요.');
  catalog=started.locations;capabilities=started.capabilities;runner=comparisonRunner(api);connected=true;
  $('team-key').value='';connectionSignature='';$('team-key').disabled=true;$('server-url').disabled=true;$('connect-live').disabled=true;setText('connect-live','서버 연결됨');$('leave-live').hidden=false;
  setText('connection-label','서버 연결됨');$('connection-dot').classList.add('connected');$('connection-dot').setAttribute('aria-label','연결됨');
  setText('connection-status','연결됐어요. 매물 정보를 입력해 주세요.');$('connection-settings').open=false;updateCapabilities();renderFill();
 }catch(e){setText('connection-status',failure(e));}finally{lock(false);}
};
$('leave-live').onclick=()=>location.reload();
if(location.protocol==='file:')setText('connection-status','start.cmd를 실행해 로컬 서버에서 열어 주세요.');

function imageError(text){setText('image-error',text);$('image-error').hidden=!text;}
function imageLoading(value){$('image-loading').hidden=!value;if(value)$('image-loading').focus();}
function setFile(next){imageError('');$('ocr-cards').hidden=true;$('ocr-cards').replaceChildren();
 if(!next)return;error('');
 if(!['image/png','image/jpeg','image/webp'].includes(next.type)){error('PNG·JPG·WebP 이미지를 선택해 주세요.');return;}
 if(next.size>8*1024*1024){error('이미지는 8MB 이하로 올려 주세요.');return;}
 file=next;extractionJob=null;if(fileUrl)URL.revokeObjectURL(fileUrl);fileUrl=URL.createObjectURL(next);
 $('image-preview').src=fileUrl;$('image-preview').hidden=false;$('upload-copy').hidden=true;document.querySelector('.upload-symbol').hidden=true;setText('upload-label','이미지 변경');
}
$('capture-file').onchange=e=>setFile(e.target.files[0]);
for(const event of ['dragenter','dragover'])$('drop-zone').addEventListener(event,e=>{e.preventDefault();if(!busy)$('drop-zone').classList.add('dragging');});
for(const event of ['dragleave','drop'])$('drop-zone').addEventListener(event,e=>{e.preventDefault();$('drop-zone').classList.remove('dragging');if(event==='drop'&&!busy)setFile(e.dataTransfer.files[0]);});
$('ocr-site').onchange=()=>{imageError('');extractionJob=null;$('ocr-cards').hidden=true;$('ocr-cards').replaceChildren();};
function renderOcrCards(response){
 const box=$('ocr-cards');box.hidden=false;
 box.innerHTML='<h3>확인할 월세 매물을 선택해 주세요</h3><p class="helper">두 엔진이 일치하게 읽은 값도 원본과 확인해 주세요. 전세와 판독이 엇갈린 매물은 선택할 수 없어요.</p>'+response.ocr_cards.map((card,index)=>{
  const f=card.fields||{},read=name=>f[name]?.value,usable=card.status==='extracted'&&read('contract_type')==='월세';
  const label=usable?`보증금 ${money(read('deposit_10k_krw'))} · 월세 ${money(read('rent_10k_krw'))} / ${read('area_m2')}㎡ · 관리비 ${money(read('maintenance_10k_krw'))}`:read('contract_type')==='전세'?'전세 매물 · 월세 비교 대상이 아니에요':'판독 보류 · 해당 매물만 잘라 다시 올리거나 직접 입력해 주세요';
  return `<button type="button" class="ocr-card button secondary" data-ocr-index="${index}" ${usable?'':'disabled'}>${escape(label)}${usable&&card.warnings?.length?'<br>인식값을 원본과 다시 확인해 주세요.':''}</button>`;
 }).join('');
 box.querySelectorAll('[data-ocr-index]:not(:disabled)').forEach(button=>button.onclick=async()=>{
  if(busy)return;lock(true);error('');
  try{const draft=await api.selectOcrCard(response.extraction_id,Number(button.dataset.ocrIndex));state=applyDraft(initialState(),draft);runner.clear();box.hidden=true;renderCollected();show('collect');}
  catch(e){error(failure(e));}finally{lock(false);}
 });
 box.scrollIntoView({block:'nearest'});
}
$('extract').onclick=async()=>{
 if(busy||!requireConnection())return;if(!file){error('분석할 이미지를 먼저 첨부해 주세요.');return;}
 lock(true);error('');imageError('');$('ocr-cards').hidden=true;progress('');imageLoading(true);
 try{extractionJob??=api.createExtraction(file,{site:capabilities.image_provider==='LOCAL_OCR'?$('ocr-site').value:null,local:capabilities.image_provider==='LOCAL_OCR'});const response=await extractionJob.run();if(response.extraction_status==='MULTIPLE_LISTINGS'&&response.ocr_cards?.length){renderOcrCards(response);progress('');return;}if(response.extraction_status!=='EXTRACTED_NEEDS_REVIEW')throw new Error(response.extraction_status==='NO_LISTING_FOUND'?'이미지 처리는 완료됐지만 입력 가능한 매물을 찾지 못했어요. 보증금·월세·면적·관리비가 함께 보이는 다방/직방 목록 영역을 올려 주세요. 지도·위치 안내·상세 페이지는 현재 지원하지 않아요. 진단: NO_LISTING_FOUND (매물 0건)':'판독한 값을 자동 입력할 수 없어 확인이 필요해요. 해당 매물의 목록 영역만 잘라 다시 올리거나 직접 입력해 주세요. 진단: EXTRACTION_REVIEW_REQUIRED');state=applyDraft(initialState(),response);runner.clear();renderCollected();show('collect');}
 catch(e){progress('');imageError('이미지에서 매물 정보를 확인하지 못했어요. 다른 이미지를 올리거나 직접 입력해 주세요.');}
 finally{imageLoading(false);lock(false);if(!$('image-error').hidden){$('image-error').scrollIntoView({block:'center'});$('image-error').focus({preventScroll:true});}else if(screen==='collect')document.querySelector('[data-screen=collect] h2')?.focus({preventScroll:true});else if(!$('ocr-cards').hidden)$('ocr-cards').scrollIntoView({block:'nearest'});}
};
$('address-search-form').onsubmit=async e=>{
 e.preventDefault();if(busy)return;
 closeAddressSearch();error('');const request=++postcodeRequest;
 $('postcode-search').hidden=false;$('postcode-loading').hidden=false;$('search').disabled=true;$('search').setAttribute('aria-expanded','true');renderAddresses();
 const failed=message=>{if(request!==postcodeRequest)return;closeAddressSearch();error(message);$('search').focus();};
 try{
  const Postcode=await loadPostcode();if(request!==postcodeRequest)return;
  postcodeTimer=setTimeout(()=>failed('카카오 주소검색이 응답하지 않아요. 인터넷 연결을 확인한 뒤 다시 검색해 주세요.'),15000);
  new Postcode({
   width:'100%',height:'100%',autoMapping:false,
   theme:{bgColor:'#EAF0FF',searchBgColor:'#FFFFFF',contentBgColor:'#FFFFFF',pageBgColor:'#FFFFFF',textColor:'#222222',queryTextColor:'#222222',postcodeTextColor:'#326CF9',emphTextColor:'#326CF9',outlineColor:'#DFDFDF'},
   onresize:size=>{if(request!==postcodeRequest)return;clearTimeout(postcodeTimer);$('postcode-loading').hidden=true;$('postcode-embed').style.height=Math.max(300,Number(size.height)||400)+'px';},
   oncomplete:data=>{
    if(request!==postcodeRequest)return;
    try{const address=normalizePostcode(data);closeAddressSearch();candidates=[address];chosenAddress=0;$('query').value=address.selected_address_text;renderAddresses();setText('search-note','선택한 주소가 맞는지 확인해 주세요.');$('address-results').scrollIntoView({block:'nearest'});if(!$('address-next').disabled)$('address-next').focus({preventScroll:true});}
    catch(e){failed(e.message);}
   }
  }).embed($('postcode-embed'),{q:$('query').value.trim(),autoClose:false});
  $('search').disabled=false;$('postcode-search').scrollIntoView({block:'nearest'});
 }catch(e){failed(e.message);}
};
function closeAddressSearch(){postcodeRequest++;clearTimeout(postcodeTimer);$('postcode-search').hidden=true;$('postcode-embed').replaceChildren();$('postcode-embed').style.height='400px';$('search').disabled=false;$('search').setAttribute('aria-expanded','false');renderAddresses();}
$('postcode-close').onclick=()=>{closeAddressSearch();$('search').focus();};
$('postcode-search').onkeydown=e=>{if(e.key==='Escape'){closeAddressSearch();$('search').focus();}};
$('query').oninput=()=>{closeAddressSearch();chosenAddress=null;candidates=[];renderAddresses();setText('search-note','카카오 주소검색에서 정확한 주소를 선택해 주세요.');};
function renderAddresses(){
 const address=candidates[chosenAddress],unsupported=connected&&address&&!isSupportedAddress(address,catalog);
 $('address-results').innerHTML=address?`<div class="candidate selected-address"><div class="title-row"><span class="selection-label"><img class="icon location-icon" src="./images/icons/Icon7.png" alt="" aria-hidden="true" width="12" height="15"> 선택한 주소</span><span>우편번호 ${escape(address.postcode)}</span></div><strong>${escape(address.selected_address_text)}</strong><span>${escape([address.selected_address_text===address.road_address_text?address.address_text:address.road_address_text,address.building_name].filter(Boolean).join(' · '))}</span></div>`:'';
 $('address-next').disabled=!address||Boolean(unsupported)||!$('postcode-search').hidden;
 $('address-capability').hidden=!unsupported;setText('address-capability',unsupported?'선택한 주소는 현재 분석 지원 지역에 포함되지 않아요. 지원 지역의 매물 주소를 선택해 주세요.':'');
}
$('address-next').onclick=()=>{
 if($('address-next').disabled||chosenAddress===null)return;state=applyAddress(state,candidates[chosenAddress]);invalidate();
 if(addressBack==='fill'){renderFill();show('fill');addressBack='start';}else{renderCollected();show('collect');}
};
function display(field,value){if(value===''||value==null)return '확인 필요';return (field==='type'?types[value]:field==='basis'?bases[value]:field==='floorType'?floors[value]:null)||value;}
const dataRow=(label,value,extra='')=>`<div class="data-row ${extra}"><span>${escape(label)}</span><strong>${escape(value)}</strong></div>`;
function renderCollected(){
 const v=state.values;setText('collected-region',v.address||regionLabel(state,catalog));
 const rows=[['주택 유형',display('type',v.type)],['면적',v.area?v.area+'㎡ · '+display('basis',v.basis):'확인 필요'],['보증금 / 월세',v.deposit!==''&&v.rent!==''?`${v.deposit} / ${v.rent}만 원`:'확인 필요'],['건축연도',v.year?v.year+'년':'확인 필요'],['월 관리비',v.maintenance!==''?money(number(v.maintenance)):'확인 필요']];
 $('collected').innerHTML=rows.map(([a,b])=>dataRow(a,b)).join('')+`<p class="data-origin">${state.sourceId?'사진에서 읽은 정보 · 지역과 매물 조건 확인 필요':'주소 검색 결과 · 호실 조건 직접 입력'}</p>`;
 setText('collect-note',state.sourceId?'사진에서 인식한 금액과 면적을 확인해 주세요. 비교 지역은 다음 단계에서 선택할 수 있어요.':'주소 검색으로 확인한 지역이에요. 해당 호실의 면적·보증금·월세·건축연도는 직접 확인해 주세요.');
}
function renderFill(){
 const selectionCatalog=connected?catalog:localCatalog;
 const v=state.values,d=selectionCatalog.districts.find(d=>d.district_code===v.district);
 const selected=state.addressRegion?.district_code===v.district&&state.addressRegion?.legal_dong_code===v.dong?state.addressRegion:null;
 // Show Kakao's selection even before the supported-region catalog arrives.
 // These display options never modify the server catalog used to validate analysis.
 const districts=[...selectionCatalog.districts],dongs=[...(d?.dongs||[])];
 if(selected&&!d)districts.push({district_code:v.district,district_name:selected.district_name||'주소에서 선택한 시군구'});
 if(selected&&!dongs.some(dong=>dong.legal_dong_code===v.dong))dongs.push({legal_dong_code:v.dong,dong_name:selected.dong_name||'주소에서 선택한 법정동'});
 $('region-district').innerHTML='<option value="">시군구 선택</option>'+districts.map(d=>`<option value="${escape(d.district_code)}">${escape(d.district_name)}</option>`).join('');$('region-district').value=v.district;$('region-district').disabled=false;
 $('region-dong').innerHTML='<option value="">법정동 선택</option>'+dongs.map(d=>`<option value="${escape(d.legal_dong_code)}">${escape(d.dong_name)}</option>`).join('');$('region-dong').value=v.dong;$('region-dong').disabled=!v.district||!dongs.length;
 const unsupported=connected&&v.district&&v.dong&&!d?.dongs.some(dong=>dong.legal_dong_code===v.dong);
 $('region-status').hidden=!unsupported;setText('region-status',unsupported?'선택한 주소는 현재 분석 지원 지역이 아니에요. 지원 지역을 선택하거나 주소를 변경해 주세요.':'');
 document.querySelectorAll('[data-field]').forEach(el=>el.value=v[el.dataset.field]);$('confirmed').checked=state.confirmed;$('region-review').hidden=!state.reviewRequired;$('review').checked=false;
  document.querySelectorAll('[data-maintenance]').forEach(el=>el.checked=state.maintenanceItems[el.dataset.maintenance]===true);
  $('maintenance-reference-note').hidden=!maintenanceItems.some(({item})=>state.maintenanceItems[item]);
  const keys=Object.keys(state.sourceOptions).filter(k=>k in optionLabels&&!maintenanceItems.some(({field})=>field===k));
  $('extracted-options').hidden=!keys.length;
  $('option-fields').innerHTML=keys.map(key=>`<label class="field">${optionLabels[key]}<select data-option="${key}">${Object.entries(optionStates).filter(([value])=>!key.endsWith('_in_maintenance')||['UNKNOWN','INCLUDED','SEPARATE_CHARGE'].includes(value)).map(([value,label])=>`<option value="${value}" ${state.sourceOptions[key]===value?'selected':''}>${label}</option>`).join('')}</select></label>`).join('');
  $('option-fields').querySelectorAll('[data-option]').forEach(el=>el.onchange=()=>{state.sourceOptions[el.dataset.option]=el.value;invalidate();});
}
$('region-district').onchange=e=>{state=changeRegion(state,e.target.value,'');invalidate();renderFill();};
$('region-dong').onchange=e=>{state=changeRegion(state,state.values.district,e.target.value);invalidate();renderFill();};
document.querySelectorAll('[data-field]').forEach(el=>el.addEventListener('input',()=>{state.values[el.dataset.field]=el.value;state.origins[el.dataset.field]='직접 입력';invalidate();}));
document.querySelectorAll('[data-maintenance]').forEach(el=>el.onchange=()=>{state.maintenanceItems[el.dataset.maintenance]=el.checked;invalidate();$('maintenance-reference-note').hidden=!maintenanceItems.some(({item})=>state.maintenanceItems[item]);});
$('review').onchange=e=>{state.reviewRequired=!e.target.checked;invalidate();};
$('confirmed').onchange=e=>{state.confirmed=e.target.checked;};
$('change-address').onclick=()=>{closeAddressSearch();addressBack='fill';$('query').value=state.values.address;chosenAddress=null;candidates=[];renderAddresses();setText('search-note','카카오 주소검색에서 변경할 주소를 선택해 주세요.');selectMode('address');show('start');};
$('choose-manual').onclick=()=>{closeAddressSearch();addressBack='start';renderFill();show('fill');};
$('collect-next').onclick=()=>{renderFill();show('fill');};
$('collect-back').onclick=()=>show('start');
$('fill-back').onclick=()=>show('start');
$('listing-form').onsubmit=async e=>{
 e.preventDefault();if(busy||!requireConnection())return;
 const issues=validate(state,catalog);$('validation').hidden=!issues.length;setText('validation',issues.join('\n'));
 if(issues.length){$('validation').scrollIntoView({block:'center'});return;}
 lock(true);error('');
 try{const report=await runner.run(makePayload(state,catalog),step=>progress(({SAVING:'매물 정보를 저장하고 있어요.',COMPARING:'비슷한 실거래와 비교하고 있어요.',ESTIMATING_MAINTENANCE:'선택한 관리비 항목의 예상 금액을 확인하고 있어요.',LOADING_REPORT:'분석 결과를 가져오고 있어요.',DONE:'분석이 완료됐어요.'})[step]),referenceScenario(state,capabilities));renderReport(report);show('result');$('retry-maintenance')?.addEventListener('click',()=>$('listing-form').requestSubmit());}
 catch(e){progress('');error(failure(e)+'\n입력 내용은 유지했어요. 다시 비교하면 같은 작업을 이어서 처리해요.');}finally{lock(false);}
};
function summary(report){const v=report?.property?.input||{};return `<div class="panel empty-summary"><h3>입력한 매물 조건</h3>${dataRow('비교 지역',regionLabel(state,catalog))}${dataRow('주택 유형 / 면적',(types[v.building_type]||display('type',state.values.type))+' / '+(finite(v.area_m2)?v.area_m2+'㎡':'미제공'))}${dataRow('보증금 / 월세',money(v.deposit_10k_krw)+' / '+money(v.rent_10k_krw))}</div>`;}
function renderMaintenance(report){
 const view=maintenanceView(report,state);if(!view.items.length)return '';
 const failed=report.client_maintenance?.state==='FAILED';
 const note=failed?'관리비 예상 금액을 불러오지 못했어요. 월세 비교 결과는 확인할 수 있어요.':view.missing.length?'':'선택한 항목의 예상 최소 ~ 최대 금액이에요. 실제 청구액과 다를 수 있어요.';
 const sources=[...new Set(view.items.filter(row=>row.amount!==null).map(row=>row.source))].map(source=>`<p class="maintenance-source">출처: ${escape(source)}</p>`).join('');
 return `<section id="maintenance-result" class="maintenance-result" aria-label="선택한 관리비 예상 금액"><div class="panel cost-panel"><div class="cost-heading"><h3>관리비 항목 예상 금액</h3><span>월 기준</span></div>${view.items.map(row=>dataRow(row.label,row.low===null||row.high===null?'자료 없음':won(row.low)+' ~ '+won(row.high),row.low===null||row.high===null?'unavailable':'')).join('')}${view.items.length>1&&view.total!==null?dataRow('선택 항목 예상 합계',won(view.items.reduce((sum,row)=>sum+row.low,0))+' ~ '+won(view.items.reduce((sum,row)=>sum+row.high,0)),'total'):''}</div>${note?`<p class="helper">${escape(note)}</p>`:''}${failed?'<button type="button" id="retry-maintenance" class="text-button maintenance-retry">예상 금액 다시 불러오기 <img class="icon arrow-icon" src="./images/icons/Icon8.png" alt="" aria-hidden="true" width="14" height="14"></button>':''}<aside class="maintenance-help" aria-label="관리비 도움말"><h4>도움말</h4><p>관리비 예상 금액은 참고용이며, 실제 사용량에 따라 달라질 수 있어요.</p>${sources}</aside></section>`;
}
function renderReport(report){
 const v=reportView(report),r=v.result,input=report.property?.input||{},ref=r.reference||{},conditions=ref.conditions||{};
 const allowed=['COMPARED','REFERENCE_ONLY'].includes(v.status);
 const labels={INSUFFICIENT_DATA:['비교할 거래가 아직 부족해요','비슷한 조건의 거래가 적어\n신뢰할 수 있는 결과를 만들기 어려워요.'],INPUT_REVIEW_REQUIRED:['입력한 조건을 다시 확인해 주세요','면적·보증금·월세가 실제 매물과 맞는지 확인해 주세요.'],OUT_OF_SCOPE:['지원 범위를 확인해 주세요','현재 지역 또는 주택 유형은 비교를 지원하지 않아요.']};
 if(!allowed){const [title,desc]=labels[v.status]||['분석 결과를 확인할 수 없어요','조건을 확인한 뒤 다시 요청해 주세요.'];$('result-content').innerHTML=`<div class="empty-heading"><div class="empty-icon" aria-hidden="true"><img class="icon info-icon" src="./images/icons/Info5.png" alt="" aria-hidden="true" width="15" height="15"></div><h2 tabindex="-1">${title}</h2><p>${escape(desc).replace(/\n/g,'<br>')}</p></div>${summary(report)}<p class="result-notes">${escape(v.status==='INSUFFICIENT_DATA'?'입력한 면적과 주택 유형이 맞는지 다시 확인해 주세요.':'지역과 매물 조건을 확인한 뒤 다시 비교해 주세요.')}</p>${renderMaintenance(report)}`;setText('real-edit-label','입력 조건 확인하기');return;}
 setText('real-edit-label','조건 수정하고 다시 비교하기');
 const judged=v.status==='COMPARED'&&v.label&&finite(v.difference);
 const title=judged?(v.difference===0?'기준 월세와 같아요':`월 ${Math.abs(v.difference).toLocaleString('ko-KR',{maximumFractionDigits:2})}만 원 ${v.difference<0?'낮아요':'높아요'}`):v.status==='REFERENCE_ONLY'?'참고용 월세 범위예요':'월세 비교 결과예요';
 const own=input.rent_10k_krw,max=Math.max(finite(own)?own:0,v.median||0)*1.15;
 const bar=(label,value,cls)=>`<div class="barrow"><span>${label}</span><div class="track"><div class="bar ${cls}" style="width:${max>0?Math.min(100,Math.max(0,value/max*100)):0}%"></div></div><strong>${escape(money(value))}</strong></div>`;
 const chart=finite(own)&&finite(v.median)?`<div class="chart" role="img" aria-label="${escape('내 매물 '+money(own)+', 유사 거래 '+money(v.median))}">${bar('내 매물',own,'own')}${bar('유사 거래',v.median,'')}</div>`:'';
 const evidenceRows=[['거래 수',finite(r.sample_count)?r.sample_count+'건':'미제공'],['비교 범위',conditions.scope||'미제공'],['거래 기간',finite(ref.months_used)?'기준일 이전 '+ref.months_used+'개월':'미제공'],['면적 허용 범위',finite(conditions.area_tolerance)?'±'+Math.round(conditions.area_tolerance*100)+'%':'미제공'],['보증금 허용 범위',finite(conditions.deposit_tolerance)?'±'+Math.round(conditions.deposit_tolerance*100)+'%':'미제공'],['건축연도 허용 범위',finite(conditions.built_year_tolerance)?'±'+conditions.built_year_tolerance+'년':'제한 없음 또는 미제공'],['신뢰도',({HIGH:'높음',MEDIUM:'보통',LOW:'낮음',NONE:'판정 불가'})[r.confidence_grade]||'미제공'],['자료 기준일',r.data_as_of||'미제공'],['출처',r.data_source||ref.source||'미제공']];
 if(judged&&v.percent!==null)evidenceRows.splice(1,0,['월세 차이율',v.percent.toFixed(1)+'%']);
 const messages=(Array.isArray(r.messages)?r.messages:[]).filter(x=>typeof x==='string'&&!/\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/.test(x)&&!/^\s*[A-Z0-9_]+\s*$/.test(x));

 $('result-content').innerHTML=`<h2 tabindex="-1">우리 동네 매물과 비교해 봤어요</h2><details class="property-details panel"><summary>${escape(regionLabel(state,catalog))} · ${escape(types[input.building_type]||display('type',state.values.type))} · ${escape(finite(input.area_m2)?input.area_m2+'㎡':'면적 미확인')}</summary><div class="property-costs">${dataRow('보증금',money(input.deposit_10k_krw))}${dataRow('월세',money(own))}${dataRow('관리비',v.maintenance===null?'미입력':money(v.maintenance))}</div></details>
 <div class="result-hero"><span class="eyebrow">${judged?'유사 실거래 기준 월세보다':'유사 실거래 비교'}</span><div class="big">${escape(title)}</div><p>내 매물 ${escape(money(own))} · 비교 기준 ${escape(money(v.median))}</p>${v.status==='REFERENCE_ONLY'?'<p class="helper">조건이 충분히 일치하지 않아 가격의 높고 낮음을 판정하지 않아요.</p>':''}</div>
 <section class="panel rent-comparison"><div class="title-row"><h3>월세 비교</h3><span class="badge">${finite(r.sample_count)?r.sample_count+'건 비교':'거래 수 미제공'}</span></div>${chart}
 <div class="panel range-panel"><div class="title-row"><span>유사 거래 월세 범위</span><strong>${v.q25!==null&&v.q75!==null?escape(v.q25+'~'+v.q75+'만 원'):'미제공'}</strong></div><p class="helper">중간 50% 범위 · ${escape(conditions.scope||'비교 범위 미제공')}</p></div>
 <details class="evidence"><summary>비교 근거 자세히 보기</summary>${evidenceRows.map(([a,b])=>dataRow(a,b)).join('')}<p class="helper">${escape(messages.join('\n'))}</p></details></section>
 ${renderMaintenance(report)}`;
}
$('real-edit').onclick=()=>{invalidate();renderFill();show('fill');};
$('real-new').onclick=()=>{imageError('');$('ocr-cards').hidden=true;$('ocr-cards').replaceChildren();state=initialState();runner?.clear();file=null;extractionJob=null;if(fileUrl)URL.revokeObjectURL(fileUrl);fileUrl=null;$('image-preview').removeAttribute('src');$('image-preview').hidden=true;$('capture-file').value='';$('upload-copy').hidden=false;document.querySelector('.upload-symbol').hidden=false;setText('upload-label','이미지 파일 첨부');candidates=[];chosenAddress=null;$('query').value='';setText('search-note','');renderAddresses();addressBack='start';selectMode('capture');show('start');};
renderFill();updateCapabilities();show('start');

// Public presentation build: same-origin gateway supplies the key on the server only.
(async()=>{
 try {
  const response=await fetch('/public-config.json',{cache:'no-store'});
  if(!response.ok || !(await response.json()).auto_connect)return;
  $('connection-settings').hidden=true;
  $('server-url').value=location.origin;
  $('team-key').value='';
  await $('connection-form').onsubmit({preventDefault(){}});
  if(!connected)error('분석 서버를 준비하고 있어요. 잠시 후 페이지를 새로고침해 주세요.');
 }catch{error('분석 서버 연결을 확인하지 못했어요. 잠시 후 새로고침해 주세요.');}
})();
