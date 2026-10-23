"""Start a separate public demo without restarting the existing API or database."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import httpx
from .team_server import SHA256


def run(runtime):
    runtime = runtime.resolve()
    key = runtime / 'team-access.key'
    exe = runtime / 'cloudflared.exe'
    if not key.is_file() or hashlib.sha256(exe.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError('Existing verified runtime is required')
    with httpx.Client(trust_env=False) as c:
        c.get('http://127.0.0.1:8012/ready', headers={'X-Team-Key': key.read_text().strip()}).raise_for_status()
        try:
            c.get('http://127.0.0.1:8013/public-config.json')
        except httpx.ConnectError:
            pass
        else:
            raise RuntimeError('Public gateway already running')
    env = dict(os.environ, PUBLIC_GATEWAY_KEY_FILE=str(key))
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    children = []
    try:
        with (runtime / 'public-gateway.log').open('ab') as log:
            children.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app.public_gateway:from_environment', '--factory', '--host', '127.0.0.1', '--port', '8013', '--no-access-log'], env=env, stdout=log, stderr=log, creationflags=flags))
        tunnel_log = runtime / 'public-tunnel.log'
        with tunnel_log.open('wb') as log:
            children.append(subprocess.Popen([str(exe), 'tunnel', '--url', 'http://127.0.0.1:8013', '--no-autoupdate'], stdout=log, stderr=log, creationflags=flags))
        for _ in range(60):
            if any(p.poll() is not None for p in children):
                raise RuntimeError('Public demo startup failed; inspect private runtime logs')
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', tunnel_log.read_text(errors='replace'))
            if match:
                (runtime / 'public-connection.json').write_text(json.dumps({'url': match[0], 'temporary': True, 'pids': [p.pid for p in children]}), encoding='utf-8')
                break
            time.sleep(1)
        else:
            raise RuntimeError('Public URL not ready')
        while not (runtime / 'public-stop.request').exists():
            if any(p.poll() is not None for p in children):
                raise RuntimeError('Public demo stopped')
            time.sleep(2)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        (runtime / 'public-connection.json').unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', required=True, type=Path)
    run(parser.parse_args().runtime)
