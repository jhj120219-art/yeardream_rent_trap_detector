"""CI-only smoke of the deployment Compose against an isolated MySQL service.
Never run this against an operational DATABASE_URL. Uses MYSQL_TEST_DATABASE_URL only.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

import httpx

from backend.app.config import ROOT
from backend.scripts.import_data import import_raw
from backend.tests.test_backend import payload, raw_rows


def main():
    url = os.getenv('MYSQL_TEST_DATABASE_URL', '')
    if '@127.0.0.1:3306/' not in url:
        raise RuntimeError('CI smoke requires the disposable localhost MySQL test service')
    with tempfile.TemporaryDirectory() as directory:
        runtime = Path(directory)
        runtime.chmod(0o755)
        keys = runtime / 'secrets'
        keys.mkdir(mode=0o755)
        key = secrets.token_urlsafe(48)
        (keys / 'team-access.key').write_text(key)
        (keys / 'team-access.key').chmod(0o644)  # Disposable runner only, container UID 10001.
        raw, clean = runtime / 'raw.csv', runtime / 'clean.csv'
        raw_rows().to_csv(raw, index=False)
        import_raw(raw, clean)
        clean.chmod(0o644)
        envfile = runtime / 'backend.env'
        envfile.write_text('DATABASE_URL=' + url.replace('@127.0.0.1:3306/', '@host.docker.internal:3306/') +
                           '\nCORS_ORIGINS=https://frontend.test.invalid\n')
        envfile.chmod(0o600)
        override = runtime / 'ci-compose.json'
        override.write_text(json.dumps({'services': {'backend': {
            'extra_hosts': ['host.docker.internal:host-gateway']}}}))
        env = dict(os.environ, BACKEND_ENV_FILE=str(envfile), RENT_DATA_FILE=str(clean),
                   RUNTIME_SECRETS_DIR=str(keys), BACKEND_IMAGE='rent-backend:ci')
        compose = ['docker', 'compose', '-p', 'rent-deploy-ci', '-f', str(ROOT/'backend/compose.deploy.yml'),
                   '-f', str(override)]
        def command(arguments, phase):
            result = subprocess.run(arguments, env=env, cwd=ROOT, capture_output=True, text=True, timeout=180)
            if result.returncode:
                # Never dump subprocess output which may contain env-file values.
                raise RuntimeError('Deployment smoke failed at: ' + phase)
            print('OK:', phase, flush=True)
            return result.stdout.strip()
        try:
            command(compose + ['config', '--quiet'], 'Compose validation')
            command(compose + ['run', '--rm', '--no-deps', 'backend', 'python', '-m',
                               'backend.scripts.init_mysql'], 'Explicit schema initialization')
            command(compose + ['run', '--rm', '--no-deps', 'backend', 'python', '-m',
                               'backend.scripts.deploy_preflight', '--allow-private-network'], 'Read-only deployment preflight')
            command(compose + ['run', '--rm', '--no-deps', 'backend', 'python', '-c',
                               "from pathlib import Path; assert not list(Path('/app').rglob('.env.context-probe')); "
                               "assert not Path('/app/backend/data/image-private.csv').exists()"], 'Private files excluded from image')
            command(compose + ['up', '-d', '--no-build', '--wait', '--wait-timeout', '90'], 'Start protected read-only container')
            with httpx.Client(base_url='http://127.0.0.1:8000', trust_env=False, timeout=10) as client:
                assert client.get('/health').status_code == 401
                client.headers['X-Team-Key'] = key
                assert client.get('/ready').status_code == 200
                assert client.get('/capabilities').json()['maintenance_enabled'] is False
                token = client.post('/sessions').json()['token']
                client.headers['Authorization'] = 'Bearer ' + token
                response = client.post('/listings', json=payload())
                assert response.status_code == 201
                listing = response.json()
                response = client.post('/listings/' + listing['id'] + '/analyses')
                assert response.status_code == 201
                analysis = response.json()
                assert analysis['result']['status'] == 'COMPARED'
                command(compose + ['restart', 'backend'], 'Restart API container')
                for _ in range(90):
                    try:
                        if client.get('/ready').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(1)
                else:
                    raise RuntimeError('Restarted API not ready')
                try:
                    assert client.get('/listings/' + listing['id']).json() == listing
                    assert client.get('/analyses/' + analysis['id']).json() == analysis
                    print('OK: persisted listing and analysis after container restart', flush=True)
                finally:
                    assert client.delete('/sessions/current').status_code == 204
                assert client.get('/listings').status_code == 401
                print('OK: shared access protection, maintenance hold and session cleanup', flush=True)
        finally:
            command(compose + ['down'], 'Remove CI API containers')


if __name__ == '__main__':
    main()
