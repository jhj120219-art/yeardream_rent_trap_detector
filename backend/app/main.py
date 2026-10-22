from contextlib import asynccontextmanager
from pathlib import Path
import secrets
import json
from typing import Literal
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, Query, Form
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from .config import Settings
from .db import Store, InvalidReference, RequestConflict, digest, now
from .schemas import ListingInput
from . import analysis_service as service
from .vision import extract_image
from .local_ocr import extract_local, choose_card, runtime_status
from .address import search_address
from .maintenance import Evidence, compare as compare_maintenance
from .maintenance import load_public_cases
from .report import build_report
from .input_review import listing_draft
from .request_diagnostics import RequestDiagnostics
from .utility_estimate import UtilityScenario, estimate as estimate_utilities, catalog as utility_catalog
from .service_identity import SERVICE_NAME, public_identity
from .card_consensus import CardConsensusSaveRequest, extraction_result as consensus_extraction_result, CardConsensusRequest, ConsensusUnavailable, run as run_card_consensus
from .machine_reference import ReferenceScenario, ReferenceUnavailable, calculate as calculate_reference
from .machine_maintenance import MachineScenario, MachineUnavailable, preview as machine_preview, report_references


def create_app(settings=None, pool=None, extractor=None):
    settings = settings or Settings()
    if settings.analysis_engine not in ('v1','v2'):
        raise ValueError('ANALYSIS_ENGINE must be v1 or v2')
    team_key = ""
    if settings.shared_mode:
        if not settings.team_key_file or '*' in settings.cors_origins:
            raise ValueError('공유 서버에는 접속키 파일과 명시적인 프론트 주소가 필요합니다.')
        team_key = Path(settings.team_key_file).read_text(encoding='utf-8').strip()
        if len(team_key) < 40 or not team_key.isascii():
            raise ValueError('공유 서버 접속키는 ASCII 40자 이상이어야 합니다.')

    @asynccontextmanager
    async def lifespan(app):
        app.state.ocr_runtime = runtime_status(settings)
        app.state.store = Store(settings.db_path, database_url=settings.database_url, initialize=settings.db_auto_init)
        app.state.pool = pool
        app.state.data_status = "READY" if pool is not None else "MISSING"
        if pool is None and settings.clean_csv.is_file():
            try:
                app.state.pool = service.load_pool(settings.clean_csv)
                app.state.data_status = "READY"
            except (ValueError,KeyError,TypeError,OSError):
                app.state.data_status = "INVALID"
        app.state.v2=None
        app.state.v2_status='DISABLED'
        if settings.v2_enabled or settings.analysis_engine=='v2':
            try:
                from .analysis_v2 import V2Service
                app.state.v2=V2Service(settings.clean_csv,settings.building_cache,settings.same_building_enabled)
                app.state.v2_status='READY'
            except (OSError,ValueError,KeyError,TypeError,ImportError):
                app.state.v2_status='UNAVAILABLE'
        yield

    app = FastAPI(title=SERVICE_NAME + " API",version="1.1.0",lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # 입력값(주소 등)을 에러 응답에 재노출하지 않는다.
        return JSONResponse(status_code=422, content={"detail":[{"loc":list(e['loc']),"msg":e['msg'],"type":e['type']} for e in exc.errors()]})

    @app.exception_handler(RequestConflict)
    async def request_conflict(request, exc):
        return JSONResponse(status_code=409,content={'detail':'같은 재시도 키로 다른 입력을 보냈거나 이전 결과가 삭제되었습니다. 새 작업에는 새 키를 사용해 주세요.'})

    def retry_key(value: str | None=Header(default=None,alias='Idempotency-Key',
            min_length=8,max_length=128,pattern=r'^[A-Za-z0-9._:-]+$')):
        return value

    def request_identity(operation,key,body):
        return (operation,key,digest(json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False))) if key is not None else None

    @app.middleware("http")
    async def limit_body(request, call_next):
        if settings.shared_mode and not secrets.compare_digest(
                request.headers.get('X-Team-Key', '').encode('utf-8'), team_key.encode('ascii')):
            return JSONResponse(status_code=401, content={'detail':'팀 접속키가 필요합니다.'}, headers={'Cache-Control':'no-store'})
        if not settings.maintenance_enabled and any(part in request.url.path.split('/') for part in
                ('maintenance', 'maintenance-evidence', 'utilities', 'utility-estimates', 'maintenance-reference', 'maintenance-references')):
            return JSONResponse(status_code=503, content={'detail':'관리비·공과금 기능은 자료 검증 중으로 보류합니다.'})
        # chunked 업로드도 제한한다. 내부 상세 예외나 API 키를 응답으로 보내지 않는다.
        size=0
        chunks=[]
        async for chunk in request.stream():
            size+=len(chunk)
            if size>9*1024*1024:
                return JSONResponse(status_code=413,content={"detail":"요청은 9MB 이하로 보내 주세요."})
            chunks.append(chunk)
        request._body=b''.join(chunks)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        return response

    def owner(authorization: str | None = Header(default=None)):
        if not authorization or not authorization.startswith('Bearer '):
            raise HTTPException(401,"세션 토큰이 필요합니다.")
        sid=app.state.store.owner(authorization[7:])
        if not sid:
            raise HTTPException(401,"유효하지 않은 세션입니다.")
        return sid

    def find(oid, sid, kind):
        obj=app.state.store.get(oid,sid,kind)
        if obj is None:
            raise HTTPException(404,"자료를 찾을 수 없습니다.")
        return obj

    @app.get('/health')
    def health():
        return {"status":"ok","schema_version":"1.1","data_status":app.state.data_status,"vision_configured":app.state.ocr_runtime['state']=='CONFIGURED' if settings.local_ocr_enabled else bool(settings.openai_key and settings.vision_model)}

    @app.get('/capabilities')
    def capabilities():
        return {
            "service": public_identity(),
            "schema_version": "1.1", "data_status": app.state.data_status,
            "loaded_coverage": service.coverage(app.state.pool),
            "address_configured": bool(settings.kakao_key),
            "image_provider": "LOCAL_OCR" if settings.local_ocr_enabled else "OPENAI",
            "vision_configured": app.state.ocr_runtime['state']=='CONFIGURED' if settings.local_ocr_enabled else bool(settings.openai_key and settings.vision_model),
            "local_ocr_runtime": app.state.ocr_runtime['state'],
            "local_ocr_sites": app.state.ocr_runtime['sites'],
            "same_building_first": settings.analysis_engine=='v2' and app.state.v2 is not None and bool(app.state.v2.cache),
            "comparable_transactions_available": False,
            "search_scope": "DONG_THEN_RELAXED_THEN_DISTRICT",
            "maintenance_enabled": settings.maintenance_enabled,
            "machine_maintenance_enabled": settings.machine_maintenance_enabled,
            "machine_maintenance_preview": settings.machine_preview_enabled,
            "advertised_costs_input_supported": True,
            "advertised_cost_categories": ["ELECTRICITY","WATER","GAS","INTERNET","OTHER"],
            "advertised_cost_category_version": "FIVE_ITEMS_V1",
            "team_access_required": settings.shared_mode,
            "location_catalog_available": hasattr(app.state.pool,'backend_locations'),
            "retry_key_supported": True,
            "analysis_engine": settings.analysis_engine,
            "v2_status": app.state.v2_status,
            "same_building_first_supported": settings.same_building_enabled and app.state.v2 is not None,
            "building_cache_status": app.state.v2.cache_status if app.state.v2 else 'NOT_LOADED',
            "note": "로드된 계약 범위이며 개별 매물의 비교 가능성이나 정확도를 보장하지 않습니다.",
        }

    @app.get('/locations')
    def locations(district_code: str | None=Query(default=None,pattern=r'^[0-9]{5}$')):
        if app.state.pool is None or not hasattr(app.state.pool,'backend_locations'):
            raise HTTPException(503,'실거래 데이터의 지역 목록이 준비되지 않았습니다.')
        districts=app.state.pool.backend_locations
        if district_code is not None:
            districts=[x for x in districts if x['district_code']==district_code]
            if not districts:
                raise HTTPException(404,'현재 데이터에서 지원하는 자치구가 아닙니다.')
        return {'source':'LOADED_NEW_RENT_CONTRACTS','data_as_of':str(app.state.pool.max_date.date()),
                'districts':districts,'note':'법정동 선택용 실거래 데이터 범위입니다. 건물 주소 검색·같은 건물 비교·개별 매물 분석 가능성을 보장하지 않습니다.'}

    @app.get('/ready', include_in_schema=False)
    def ready():
        if not app.state.store.available():
            raise HTTPException(503,"DB에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.")
        if app.state.pool is None:
            raise HTTPException(503,"정제된 실거래 데이터를 연결해야 합니다.")
        if settings.analysis_engine=='v2' and app.state.v2 is None:
            raise HTTPException(503,'개선된 분석 코드와 자료 연결을 확인해야 합니다.')
        return {"status":"ready"}

    @app.post('/sessions',status_code=201)
    def session():
        return {"token":app.state.store.session(),"token_type":"Bearer"}

    @app.delete('/sessions/current',status_code=204)
    def delete_session(sid=Depends(owner)):
        app.state.store.delete_session(sid)
        return Response(status_code=204)

    @app.post('/listings',status_code=201)
    def listing(body: ListingInput, sid=Depends(owner),key=Depends(retry_key)):
        request=request_identity('POST /listings',key,body.model_dump(mode='json'))
        replayed=app.state.store.replay(sid,'listing',request)
        if replayed is not None:
            return replayed
        raw=body.model_dump(exclude={'source_extraction_id','previous_listing_id'})
        links={}
        source_id=body.source_extraction_id
        if body.previous_listing_id:
            previous=find(body.previous_listing_id,sid,'listing')
            links['previous_listing_id']=body.previous_listing_id
            source_id=source_id or previous.get('links',{}).get('source_extraction_id')
        if source_id:
            find(source_id,sid,'extraction')
            if body.confirmation.input_source != 'IMAGE_REVIEWED':
                raise HTTPException(422,'이미지 초안에서 등록할 때는 IMAGE_REVIEWED를 지정해 주세요.')
            links['source_extraction_id']=source_id
        normalized=service.review(raw)
        # 확인 전 초안도 저장할 수 있지만 분석에는 사용할 수 없다.
        try:
            return app.state.store.create(sid,'listing',{
                "input":raw,"validation":normalized,
                "confirmation_recorded_at":now() if body.confirmation.user_confirmed else None,
            },links=links,request=request)
        except InvalidReference:
            raise HTTPException(404,'자료를 찾을 수 없습니다.') from None

    @app.get('/listings')
    def list_listings(limit: int=Query(default=20,ge=1,le=50),
                      offset: int=Query(default=0,ge=0),sid=Depends(owner)):
        return app.state.store.page(sid,'listing',limit,offset)

    @app.get('/listings/{listing_id}')
    def get_listing(listing_id: str,sid=Depends(owner)):
        return find(listing_id,sid,'listing')

    @app.get('/listings/{listing_id}/report')
    def listing_report(listing_id: str, evidence_limit: int=Query(default=20,ge=1,le=50),
                       evidence_offset: int=Query(default=0,ge=0),sid=Depends(owner)):
        obj=find(listing_id,sid,'listing')
        analyses=app.state.store.children(listing_id,sid,'analysis',limit=1)['items']
        evidence=app.state.store.children(listing_id,sid,'maintenance_evidence',evidence_limit,evidence_offset)
        estimates=app.state.store.children(listing_id,sid,'utility_estimate',limit=1)['items']
        refs=report_references(obj,listing_id) if settings.machine_preview_enabled and settings.maintenance_enabled else None
        report=build_report(obj,analyses[0] if analyses else None,evidence,app.state.data_status,refs)
        stored_maintenance=app.state.store.maintenance(listing_id,sid)
        if stored_maintenance is not None:
            report['advertised_costs']=stored_maintenance
        report['utility_estimate']=estimates[0] if estimates else None
        reference_rows=app.state.store.children(listing_id,sid,'machine_reference',limit=1)['items']
        report['machine_maintenance_reference']=reference_rows[0] if reference_rows else None
        if reference_rows and settings.maintenance_enabled and settings.machine_maintenance_enabled:
            report['maintenance_reference_groups']=reference_rows[0]['groups']
        if not settings.maintenance_enabled:
            for field in ('maintenance', 'utility_costs', 'monthly_cost', 'utility_estimate', 'machine_maintenance_reference'):
                report[field]={'state':'ON_HOLD'}
            report['workflow']['next_actions']=[action for action in report['workflow']['next_actions'] if 'MAINTENANCE' not in action]
            report['workflow']['notice']='광고 관리비·포함 항목은 advertised_costs에서 확인할 수 있습니다. 관리비·공과금 비교와 예상 비용 계산은 자료 검증 중으로 보류합니다.'
        return report

    @app.post('/listings/{listing_id}/maintenance-references',status_code=201)
    def create_machine_reference(listing_id: str, body: ReferenceScenario, sid=Depends(owner),key=Depends(retry_key)):
        obj=find(listing_id,sid,'listing')
        if not settings.machine_maintenance_enabled:
            raise HTTPException(503,'분석가 관리비 참고값 연결이 활성화되지 않았습니다.')
        raw=obj['input']
        if not raw['confirmation']['user_confirmed'] or not obj['validation']['ok'] or not body.acknowledge_reference_limits:
            raise HTTPException(422,'매물 입력 확인과 참고값의 한계 확인이 필요합니다.')
        if raw.get('options',{}).get('maintenance_input_mode') != 'CHECKBOX_TOTAL_V1':
            raise HTTPException(422,'5항목 체크박스와 총액 입력을 확인해 주세요.')
        if not str(raw['listing'].get('district_code','')).startswith('11'):
            raise HTTPException(422,'서울 지역의 참고값만 지원합니다.')
        request=request_identity('POST /listings/'+listing_id+'/maintenance-references',key,body.model_dump(mode='json'))
        replayed=app.state.store.replay(sid,'machine_reference',request)
        if replayed is not None:
            return replayed
        try:
            value=calculate_reference(obj,body,settings.maintenance_machine_root)
        except ReferenceUnavailable:
            raise HTTPException(503,'관리비 분석 코드·기준자료·입출력 계약을 확인해야 합니다.') from None
        return app.state.store.create(sid,'machine_reference',value,parent=listing_id,request=request)

    @app.get('/maintenance-references/{reference_id}')
    def get_machine_reference(reference_id: str,sid=Depends(owner)):
        return find(reference_id,sid,'machine_reference')

    @app.post('/listings/{listing_id}/maintenance-reference')
    def maintenance_reference(listing_id: str, body: MachineScenario, sid=Depends(owner)):
        """Team preview endpoint, distinct from persisted maintenance-references."""
        if not settings.machine_preview_enabled:
            raise HTTPException(404,'머신 관리비 미리보기는 꺼져 있습니다.')
        obj=find(listing_id,sid,'listing')
        try:
            return machine_preview(obj,body,listing_id)
        except MachineUnavailable:
            raise HTTPException(503,'관리비 분석 코드·기준자료를 확인해야 합니다.') from None

    @app.post('/extraction/card-consensus')
    def card_consensus(body: CardConsensusRequest, sid=Depends(owner)):
        """Stateless: engine reads in, agreed values out. Single-engine values are never auto-filled."""
        try:
            return run_card_consensus(body)
        except ConsensusUnavailable:
            raise HTTPException(503,'이미지 추출 합의 모듈을 불러오지 못했습니다.') from None

    @app.post('/extractions/card-consensus', status_code=201)
    def save_card_consensus(body: CardConsensusSaveRequest, sid=Depends(owner)):
        try:
            result = run_card_consensus(body)
        except ConsensusUnavailable:
            raise HTTPException(503, '이미지 추출 합의 모듈을 불러오지 못했습니다.') from None
        if body.card_index >= len(result['cards']):
            raise HTTPException(422, '선택한 카드 번호가 결과 범위를 벗어났습니다.')
        card = result['cards'][body.card_index]
        if card['status'] != 'extracted':
            raise HTTPException(409, '합의되지 않은 카드는 자동입력 후보로 저장할 수 없습니다. 직접 확인해 입력하세요.')
        if card['fields']['contract_type']['value'] != '월세':
            raise HTTPException(422, '현재 분석 연결은 월세 매물만 지원합니다.')
        return app.state.store.create(sid, 'extraction', {'result': consensus_extraction_result(card)})

    @app.delete('/listings/{listing_id}',status_code=204)
    def delete_listing(listing_id: str,sid=Depends(owner)):
        find(listing_id,sid,'listing')
        app.state.store.delete(listing_id,sid,'listing')
        return Response(status_code=204)

    @app.post('/listings/{listing_id}/analyses',status_code=201)
    def analyze(listing_id: str,sid=Depends(owner),key=Depends(retry_key),engine: Literal['v1','v2'] | None=Query(default=None)):
        selected=engine or settings.analysis_engine
        request=request_identity('POST /listings/'+listing_id+'/analyses',key,{} if selected=='v1' else {'engine':'v2'})
        replayed=app.state.store.replay(sid,'analysis',request)
        if replayed is not None:
            return replayed
        obj=find(listing_id,sid,'listing')
        if app.state.pool is None:
            raise HTTPException(503,"실거래 데이터가 연결되지 않아 분석할 수 없습니다.")
        if selected=='v2':
            if app.state.v2 is None:
                raise HTTPException(503,'개선된 분석 코드와 자료 연결을 확인해야 합니다.')
            result=app.state.v2.run(obj['input'])
        else:
            result=service.run(obj['input'],app.state.pool)
        return app.state.store.create(sid,'analysis',{"listing_id":listing_id,"result":result},parent=listing_id,request=request)

    @app.get('/analyses/{analysis_id}')
    def get_analysis(analysis_id: str,sid=Depends(owner)):
        return find(analysis_id,sid,'analysis')

    @app.get('/addresses/search')
    async def addresses(q: str=Query(min_length=2,max_length=200),sid=Depends(owner)):
        return await search_address(q,settings)

    @app.post('/extractions',status_code=201)
    async def extraction(file: UploadFile=File(...), site: Literal["dabang", "zigbang"]=Form(default="dabang"), sid=Depends(owner)):
        data=await file.read(8*1024*1024+1)
        if len(data)>8*1024*1024:
            raise HTTPException(413,"이미지는 8MB 이하로 올려 주세요.")
        if not extractor and settings.local_ocr_enabled and app.state.ocr_runtime['state'] != 'CONFIGURED':
            raise HTTPException(503,'OCR 실행 환경이 준비되지 않았습니다. 직접 입력을 이용해 주세요.')
        result=await extractor(data,settings) if extractor else (await extract_local(data,settings,site) if settings.local_ocr_enabled else await extract_image(data,settings))
        # 원본 이미지와 파일명은 DB에 저장하지 않는다.
        return app.state.store.create(sid,'extraction',{"result":result})

    @app.get('/extractions/{extraction_id}')
    def get_extraction(extraction_id: str,sid=Depends(owner)):
        return find(extraction_id,sid,'extraction')

    @app.get('/extractions/{extraction_id}/listing-draft')
    def get_listing_draft(extraction_id: str,sid=Depends(owner)):
        source=find(extraction_id,sid,'extraction')
        return {**listing_draft(source), 'ocr_cards': source['result'].get('ocr_cards', []), 'extraction_id': extraction_id}

    @app.post('/extractions/{extraction_id}/cards/{card_index}', status_code=201)
    def select_ocr_card(extraction_id: str, card_index: int, sid=Depends(owner), key=Depends(retry_key)):
        source=find(extraction_id,sid,'extraction')
        request=request_identity('POST /extractions/'+extraction_id+'/cards',key,{'card_index':card_index})
        replayed=app.state.store.replay(sid,'extraction',request)
        if replayed is not None:
            return {**listing_draft(replayed), 'extraction_id':replayed['id']}
        result=choose_card(source['result'], card_index)
        saved=app.state.store.create(sid,'extraction', {'result': result,
            'selected_from_extraction_id':extraction_id,'selected_card_index':card_index},request=request)
        return {**listing_draft(saved),'extraction_id':saved['id']}

    @app.delete('/extractions/{extraction_id}',status_code=204)
    def delete_extraction(extraction_id: str,sid=Depends(owner)):
        find(extraction_id,sid,'extraction')
        app.state.store.delete(extraction_id,sid,'extraction')
        return Response(status_code=204)

    @app.get('/maintenance/reference-cases')
    def maintenance_cases():
        return load_public_cases()

    @app.get('/utilities/reference-catalog')
    def get_utility_catalog():
        return utility_catalog()

    @app.post('/listings/{listing_id}/utility-estimates',status_code=201)
    def utility_estimate(listing_id: str, body: UtilityScenario,sid=Depends(owner)):
        obj=find(listing_id,sid,'listing')
        return app.state.store.create(sid,'utility_estimate',{
            'listing_id':listing_id,'scenario':body.model_dump(mode='json'),
            'result':estimate_utilities(obj,body),
        },parent=listing_id)

    @app.get('/utility-estimates/{estimate_id}')
    def get_utility_estimate(estimate_id: str,sid=Depends(owner)):
        return find(estimate_id,sid,'utility_estimate')

    @app.delete('/utility-estimates/{estimate_id}',status_code=204)
    def delete_utility_estimate(estimate_id: str,sid=Depends(owner)):
        find(estimate_id,sid,'utility_estimate')
        app.state.store.delete(estimate_id,sid,'utility_estimate')
        return Response(status_code=204)

    @app.post('/listings/{listing_id}/maintenance-evidence',status_code=201)
    def maintenance_evidence(listing_id: str, body: Evidence, sid=Depends(owner)):
        obj=find(listing_id,sid,'listing')
        evidence=body.model_dump(mode='json')
        return app.state.store.create(sid,'maintenance_evidence',{
            'listing_id':listing_id,'evidence':evidence,
            'comparison':compare_maintenance(obj,evidence),
        },parent=listing_id)

    @app.get('/maintenance-evidence')
    def maintenance_history(limit: int=Query(default=20,ge=1,le=50),
                            offset: int=Query(default=0,ge=0),sid=Depends(owner)):
        return app.state.store.page(sid,'maintenance_evidence',limit,offset)

    @app.get('/maintenance-evidence/{evidence_id}')
    def get_maintenance(evidence_id: str,sid=Depends(owner)):
        return find(evidence_id,sid,'maintenance_evidence')

    @app.delete('/maintenance-evidence/{evidence_id}',status_code=204)
    def delete_maintenance(evidence_id: str,sid=Depends(owner)):
        find(evidence_id,sid,'maintenance_evidence')
        app.state.store.delete(evidence_id,sid,'maintenance_evidence')
        return Response(status_code=204)

    # CORS가 가장 바깥에서 preflight와 접속 거절 응답에도 적용되게 한다.
    app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins,allow_methods=["GET","POST","DELETE"],allow_headers=["Authorization","Content-Type","X-Team-Key","Idempotency-Key"],expose_headers=['X-Request-ID'])
    app.add_middleware(RequestDiagnostics)
    return app

app=create_app()
