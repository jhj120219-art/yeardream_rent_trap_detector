from contextlib import asynccontextmanager
from pathlib import Path
import secrets
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from .config import Settings
from .db import Store, InvalidReference, now
from .schemas import ListingInput
from . import analysis_service as service
from .vision import extract_image
from .address import search_address
from .maintenance import Evidence, compare as compare_maintenance
from .maintenance import load_public_cases
from .report import build_report
from .input_review import listing_draft
from .utility_estimate import UtilityScenario, estimate as estimate_utilities, catalog as utility_catalog


def create_app(settings=None, pool=None, extractor=None):
    settings = settings or Settings()
    team_key = ""
    if settings.shared_mode:
        if not settings.team_key_file or '*' in settings.cors_origins:
            raise ValueError('공유 서버에는 접속키 파일과 명시적인 프론트 주소가 필요합니다.')
        team_key = Path(settings.team_key_file).read_text(encoding='utf-8').strip()
        if len(team_key) < 40 or not team_key.isascii():
            raise ValueError('공유 서버 접속키는 ASCII 40자 이상이어야 합니다.')

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(settings.db_path, database_url=settings.database_url, initialize=settings.db_auto_init)
        app.state.pool = pool
        app.state.data_status = "READY" if pool is not None else "MISSING"
        if pool is None and settings.clean_csv.is_file():
            try:
                app.state.pool = service.load_pool(settings.clean_csv)
                app.state.data_status = "READY"
            except (ValueError,KeyError,TypeError,OSError):
                app.state.data_status = "INVALID"
        yield

    app = FastAPI(title="월세 비교 API",version="1.1.0",lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # 입력값(주소 등)을 에러 응답에 재노출하지 않는다.
        return JSONResponse(status_code=422, content={"detail":[{"loc":list(e['loc']),"msg":e['msg'],"type":e['type']} for e in exc.errors()]})

    @app.middleware("http")
    async def limit_body(request, call_next):
        if settings.shared_mode and not secrets.compare_digest(
                request.headers.get('X-Team-Key', '').encode('utf-8'), team_key.encode('ascii')):
            return JSONResponse(status_code=401, content={'detail':'팀 접속키가 필요합니다.'}, headers={'Cache-Control':'no-store'})
        if not settings.maintenance_enabled and any(part in request.url.path.split('/') for part in
                ('maintenance', 'maintenance-evidence', 'utilities', 'utility-estimates')):
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
        return {"status":"ok","schema_version":"1.1","data_status":app.state.data_status,"vision_configured":bool(settings.openai_key and settings.vision_model)}

    @app.get('/capabilities')
    def capabilities():
        return {
            "schema_version": "1.1", "data_status": app.state.data_status,
            "loaded_coverage": service.coverage(app.state.pool),
            "address_configured": bool(settings.kakao_key),
            "vision_configured": bool(settings.openai_key and settings.vision_model),
            "same_building_first": False,
            "comparable_transactions_available": False,
            "search_scope": "DONG_THEN_RELAXED_THEN_DISTRICT",
            "maintenance_enabled": settings.maintenance_enabled,
            "team_access_required": settings.shared_mode,
            "note": "로드된 계약 범위이며 개별 매물의 비교 가능성이나 정확도를 보장하지 않습니다.",
        }

    @app.get('/ready', include_in_schema=False)
    def ready():
        if not app.state.store.available():
            raise HTTPException(503,"DB에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.")
        if app.state.pool is None:
            raise HTTPException(503,"정제된 실거래 데이터를 연결해야 합니다.")
        return {"status":"ready"}

    @app.post('/sessions',status_code=201)
    def session():
        return {"token":app.state.store.session(),"token_type":"Bearer"}

    @app.delete('/sessions/current',status_code=204)
    def delete_session(sid=Depends(owner)):
        app.state.store.delete_session(sid)
        return Response(status_code=204)

    @app.post('/listings',status_code=201)
    def listing(body: ListingInput, sid=Depends(owner)):
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
            },links=links)
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
        report=build_report(obj,analyses[0] if analyses else None,evidence,app.state.data_status)
        report['utility_estimate']=estimates[0] if estimates else None
        if not settings.maintenance_enabled:
            for field in ('maintenance', 'utility_costs', 'monthly_cost', 'utility_estimate'):
                report[field]={'state':'ON_HOLD'}
            report['workflow']['next_actions']=[action for action in report['workflow']['next_actions'] if 'MAINTENANCE' not in action]
            report['workflow']['notice']='관리비·공과금 비교는 자료 검증 중으로 보류합니다. 월세 분석만 사용하세요.'
        return report

    @app.delete('/listings/{listing_id}',status_code=204)
    def delete_listing(listing_id: str,sid=Depends(owner)):
        find(listing_id,sid,'listing')
        app.state.store.delete(listing_id,sid,'listing')
        return Response(status_code=204)

    @app.post('/listings/{listing_id}/analyses',status_code=201)
    def analyze(listing_id: str,sid=Depends(owner)):
        obj=find(listing_id,sid,'listing')
        if app.state.pool is None:
            raise HTTPException(503,"실거래 데이터가 연결되지 않아 분석할 수 없습니다.")
        result=service.run(obj['input'],app.state.pool)
        return app.state.store.create(sid,'analysis',{"listing_id":listing_id,"result":result},parent=listing_id)

    @app.get('/analyses/{analysis_id}')
    def get_analysis(analysis_id: str,sid=Depends(owner)):
        return find(analysis_id,sid,'analysis')

    @app.get('/addresses/search')
    async def addresses(q: str=Query(min_length=2,max_length=200),sid=Depends(owner)):
        return await search_address(q,settings)

    @app.post('/extractions',status_code=201)
    async def extraction(file: UploadFile=File(...),sid=Depends(owner)):
        data=await file.read(8*1024*1024+1)
        if len(data)>8*1024*1024:
            raise HTTPException(413,"이미지는 8MB 이하로 올려 주세요.")
        result=await (extractor or extract_image)(data,settings)
        # 원본 이미지와 파일명은 DB에 저장하지 않는다.
        return app.state.store.create(sid,'extraction',{"result":result})

    @app.get('/extractions/{extraction_id}')
    def get_extraction(extraction_id: str,sid=Depends(owner)):
        return find(extraction_id,sid,'extraction')

    @app.get('/extractions/{extraction_id}/listing-draft')
    def get_listing_draft(extraction_id: str,sid=Depends(owner)):
        return listing_draft(find(extraction_id,sid,'extraction'))

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
    app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins,allow_methods=["GET","POST","DELETE"],allow_headers=["Authorization","Content-Type","X-Team-Key"])
    return app

app=create_app()
