"""실제 로컬 TCP 서버의 가상 표본 흐름 및 데이터 미연결 점검. 종료 시 서버/임시 DB 정리."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import httpx
from backend.app.config import ROOT
from backend.scripts.import_data import import_raw
from backend.tests.test_backend import payload, raw_rows


def smoke():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        raw, clean = root/'raw.csv', root/'clean.csv'
        raw_rows().to_csv(raw, index=False)
        import_raw(raw, clean)
        for ready in (True, False):
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            env = dict(os.environ, BACKEND_DB_PATH=str(root/f'{ready}.sqlite3'),
                       RENT_CLEAN_CSV=str(clean if ready else root/'missing.csv'),
                       OPENAI_API_KEY='', KAKAO_REST_API_KEY='')
            with (root/'server.log').open('w', encoding='utf-8') as log:
                process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app.main:app',
                                            '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT, env=env,
                                           stdout=log, stderr=subprocess.STDOUT)
                try:
                    with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=5, trust_env=False) as client:
                        deadline = time.monotonic()+25
                        while True:
                            if process.poll() is not None:
                                raise RuntimeError('Server exited; inspect local runtime dependencies.')
                            try:
                                health = client.get('/health')
                                break
                            except httpx.ConnectError:
                                if time.monotonic() > deadline:
                                    raise RuntimeError('Server startup timed out.') from None
                                time.sleep(0.2)
                        assert health.json()['data_status'] == ('READY' if ready else 'MISSING')
                        assert client.get('/ready').status_code == (200 if ready else 503)
                        assert client.get('/openapi.json').status_code == 200
                        client.headers['Authorization'] = 'Bearer '+client.post('/sessions').json()['token']
                        saved = client.post('/listings', json=payload())
                        assert saved.status_code == 201
                        result = client.post('/listings/'+saved.json()['id']+'/analyses')
                        assert result.status_code == (201 if ready else 503), result.text
                        if ready:
                            analysis = result.json()
                            assert analysis['result']['status'] == 'COMPARED'
                            assert client.get('/analyses/'+analysis['id']).json() == analysis
                            assert client.delete('/listings/'+saved.json()['id']).status_code == 204
                            assert client.get('/analyses/'+analysis['id']).status_code == 404
                        assert client.delete('/sessions/current').status_code == 204
                        assert client.get('/listings/'+saved.json()['id']).status_code == 401
                        print(json.dumps(dict(transport='TCP', data='SYNTHETIC' if ready else 'MISSING',
                                              health=health.json()['data_status'], analysis_http=result.status_code,
                                              session_deleted=True)))
                finally:
                    process.terminate()
                    process.wait(timeout=10)


if __name__ == '__main__':
    smoke()
