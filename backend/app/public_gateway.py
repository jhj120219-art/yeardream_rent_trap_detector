"""Same-origin demo frontend. The existing team key never reaches the browser."""
import asyncio
import re
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response

READ = re.compile(r'^/(capabilities|locations|addresses/search|extractions/[a-zA-Z0-9_-]+/listing-draft|listings/[a-zA-Z0-9_-]+/report)$')
WRITE = re.compile(r'^/(sessions|listings|extractions|extractions/[a-zA-Z0-9_-]+/cards/[0-9]+|listings/[a-zA-Z0-9_-]+/(analyses|maintenance-references))$')


def create_gateway(key_file, web_root=None, transport=None):
    key = Path(key_file).read_text(encoding='utf-8').strip()
    if len(key) < 40:
        raise ValueError('Existing team key is required')
    root = Path(web_root or Path(__file__).resolve().parents[1] / 'web').resolve()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    sessions = deque()
    slots = asyncio.Semaphore(3)

    @app.middleware('http')
    async def gateway(request: Request, call_next):
        path = request.url.path
        is_api = bool(READ.fullmatch(path) or WRITE.fullmatch(path) or path == '/sessions/current')
        if not is_api:
            return await call_next(request)
        allowed = (request.method == 'GET' and READ.fullmatch(path)) or (request.method == 'POST' and WRITE.fullmatch(path)) or (request.method == 'DELETE' and path == '/sessions/current')
        if not allowed:
            return JSONResponse({'detail': '허용되지 않은 요청입니다.'}, status_code=405)
        # This service is intentionally public, but cross-site browser writes are blocked.
        origin = request.headers.get('origin')
        if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and urlsplit(origin).netloc != request.headers.get('host')):
            return JSONResponse({'detail': '다른 사이트에서 보낸 요청입니다.'}, status_code=403)
        if request.method == 'POST' and path == '/sessions':
            now = time.monotonic()
            while sessions and sessions[0] < now - 60:
                sessions.popleft()
            if len(sessions) >= 20:
                return JSONResponse({'detail': '잠시 후 다시 시도해 주세요.'}, status_code=429)
            sessions.append(now)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 9 * 1024 * 1024:
                return Response(status_code=413)
        headers = {'X-Team-Key': key}
        for name in ('authorization', 'content-type', 'idempotency-key'):
            if name in request.headers:
                headers[name] = request.headers[name]
        try:
            async with slots, httpx.AsyncClient(base_url='http://127.0.0.1:8012', transport=transport, timeout=280, trust_env=False, follow_redirects=False) as client:
                response = await client.request(request.method, path, params=request.query_params, content=bytes(body), headers=headers)
            if response.is_redirect:
                return Response(status_code=502)
            return Response(response.content, status_code=response.status_code, headers={k: v for k, v in response.headers.items() if k.lower() in ('content-type', 'x-request-id') } | {'Cache-Control': 'no-store'})
        except httpx.HTTPError:
            return JSONResponse({'detail': '분석 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.'}, status_code=503)

    @app.get('/public-config.json')
    def config():
        return JSONResponse({'auto_connect': True}, headers={'Cache-Control': 'no-store'})

    @app.get('/{asset:path}')
    def asset(asset: str):
        target = (root / (asset or '월세비교_화면흐름.html')).resolve()
        if root not in target.parents or any(p.startswith('.') for p in target.relative_to(root).parts) or target.suffix not in {'.html', '.mjs', '.css', '.ttf', '.png'} or not target.is_file():
            return Response(status_code=404)
        return FileResponse(target, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

    return app


def from_environment():
    import os
    return create_gateway(os.environ['PUBLIC_GATEWAY_KEY_FILE'])
