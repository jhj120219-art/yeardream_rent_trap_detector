"""Request correlation without recording credentials, bodies or concrete URLs."""
import logging
import time
import uuid

logger = logging.getLogger('uvicorn.error')


class RequestDiagnostics:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request_id = uuid.uuid4().hex
        started = time.monotonic()
        status = 500

        async def correlated_send(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
                message = dict(message)
                message['headers'] = [
                    (key, value) for key, value in message.get('headers', [])
                    if key.lower() != b'x-request-id'
                ] + [(b'x-request-id', request_id.encode('ascii'))]
            await send(message)

        try:
            await self.app(scope, receive, correlated_send)
        finally:
            # Only router-defined templates are safe. Never log raw paths/query,
            # inbound request IDs, headers, bodies or exception text.
            route = scope.get('route')
            template = getattr(route, 'path', '/unmatched')
            method = scope.get('method', '')
            method = method if method in {'GET', 'POST', 'DELETE', 'OPTIONS', 'PUT', 'PATCH', 'HEAD'} else 'OTHER'
            logger.info('request_id=%s method=%s route=%s status=%s duration_ms=%.1f',
                        request_id, method, template, status,
                        (time.monotonic() - started) * 1000)
