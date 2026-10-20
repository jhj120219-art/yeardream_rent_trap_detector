"""Windows 팀 테스트 서버. 비밀/DB/실행 로그는 저장소 밖의 runtime에만 둔다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
VERSION = '2026.10.1'
SHA256 = '4d2490e74082c5d48dbfedaf92576fa5bd1702379ab88eb7faa0cfbe8dc891b6'
DOWNLOAD = f'https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/cloudflared-windows-amd64.exe'


def backup(database, destination):
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3')
    with sqlite3.connect(str(database)) as source, sqlite3.connect(str(target)) as output:
        source.backup(output)
        if output.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('백업 검증 실패')
    return target


def request(base, key, path='/ready'):
    req = urllib.request.Request(base + path, headers={'X-Team-Key': key})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def run(runtime, port):
    runtime = runtime.resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    keyfile = runtime / 'team-access.key'
    if not keyfile.exists():
        keyfile.write_text(secrets.token_urlsafe(48), encoding='utf-8')
    key = keyfile.read_text(encoding='utf-8').strip()
    executable = runtime / 'cloudflared.exe'
    if not executable.exists():
        urllib.request.urlretrieve(DOWNLOAD, executable)
    if hashlib.sha256(executable.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError('공식 터널 파일 해시가 다릅니다. 실행하지 않습니다.')
    csv = ROOT / 'backend/data/clean_rent_data.csv'
    if not csv.is_file():
        raise RuntimeError('실거래 정제 CSV 연결이 필요합니다.')
    mysql_mode = bool(os.getenv('DATABASE_URL'))
    database = runtime / 'team.sqlite3'
    if not mysql_mode and database.exists():
        backup(database, runtime / 'backups')
    origins_file = runtime / 'frontend-origins.txt'
    if not origins_file.exists():
        origins_file.write_text('http://localhost:5173\nhttp://localhost:3000\n', encoding='utf-8')
    origins = ','.join(x.strip() for x in origins_file.read_text(encoding='utf-8').splitlines() if x.strip())
    env = dict(os.environ, BACKEND_DB_PATH='' if mysql_mode else str(database), RENT_CLEAN_CSV=str(csv),
               TEAM_ACCESS_KEY_FILE=str(keyfile), TEAM_SHARED_MODE='true',
               MAINTENANCE_ENABLED='false', CORS_ORIGINS=origins)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    base = f'http://127.0.0.1:{port}'
    server = tunnel = None
    try:
        with (runtime / 'server.log').open('w', encoding='utf-8') as log:
            server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app.main:app',
                '--host', '127.0.0.1', '--port', str(port), '--no-access-log'],
                cwd=ROOT, env=env, stdout=log, stderr=log, creationflags=flags)
            for _ in range(60):
                if server.poll() is not None:
                    raise RuntimeError('팀 서버 시작 실패: server.log 확인')
                try:
                    request(base, key)
                    break
                except Exception:
                    time.sleep(1)
            else:
                raise RuntimeError('실거래 데이터 로딩 시간 초과')
            # 키 없는 서버가 외부로 공개되지 않도록 터널 시작 전에 검사한다.
            try:
                urllib.request.urlopen(base + '/sessions', timeout=5)
            except urllib.error.HTTPError as error:
                if error.code != 401:
                    raise
            else:
                raise RuntimeError('접속 보호 검증 실패')
            with (runtime / 'tunnel.log').open('w', encoding='utf-8') as tunnel_log:
                tunnel = subprocess.Popen([str(executable), 'tunnel', '--url', base,
                    '--protocol', 'http2', '--no-autoupdate'], stdout=tunnel_log,
                    stderr=tunnel_log, creationflags=flags, cwd=runtime)
                for _ in range(60):
                    if tunnel.poll() is not None:
                        raise RuntimeError('외부 연결 실패: tunnel.log 확인')
                    content = (runtime / 'tunnel.log').read_text(encoding='utf-8', errors='replace')
                    urls = re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com', content)
                    if urls:
                        url = urls[-1]
                        break
                    time.sleep(1)
                else:
                    raise RuntimeError('외부 주소 생성 시간 초과')
                # A generated hostname can precede DNS/tunnel registration. Publish it only
                # after authenticated HTTPS readiness succeeds, not merely after a log line.
                for attempt in range(60):
                    if server.poll() is not None or tunnel.poll() is not None:
                        raise RuntimeError('외부 연결 준비 중 서버가 중단됐습니다.')
                    try:
                        if request(url,key).get('status')=='ready':
                            break
                    except Exception:
                        pass
                    if attempt<59:
                        time.sleep(1)
                else:
                    raise RuntimeError('외부 HTTPS 연결 준비 시간 초과. 주소를 공유하지 않았습니다.')
                info = dict(url=url, port=port, supervisor_pid=os.getpid(), server_pid=server.pid,
                            tunnel_pid=tunnel.pid, database='mysql (DATABASE_URL)' if mysql_mode else str(database), key_file=str(keyfile),
                            temporary=True, cloudflared_version=VERSION, cloudflared_sha256=SHA256)
                (runtime / 'connection.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
                (runtime / '접속주소.txt').write_text(url+'\n접속키는 team-access.key 파일을 별도로 전달하세요.\n', encoding='utf-8')
                if not mysql_mode:
                    backup(database, runtime / 'backups')
                next_backup = time.monotonic() + 86400
                while not (runtime / 'stop.request').exists():
                    if server.poll() is not None or tunnel.poll() is not None:
                        raise RuntimeError('서버 또는 터널 중단. 로그를 확인하고 다시 시작하세요.')
                    if not mysql_mode and time.monotonic() >= next_backup:
                        backup(database, runtime / 'backups')
                        next_backup = time.monotonic() + 86400
                    time.sleep(2)
    finally:
        for process in (tunnel, server):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        if not mysql_mode and database.exists():
            backup(database, runtime / 'backups')
        (runtime / 'stop.request').unlink(missing_ok=True)
        (runtime / 'connection.json').unlink(missing_ok=True)
        (runtime / '접속주소.txt').write_text('현재 서버가 꺼져 있습니다. 시작 후 주소가 새로 생성됩니다.\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8012)
    parser.add_argument('--env-file', type=Path, help='Private environment file; never put credentials in command arguments')
    args = parser.parse_args()
    if args.env_file:
        from dotenv import load_dotenv
        if not args.env_file.is_file():
            parser.error('Private environment file does not exist')
        load_dotenv(args.env_file, override=True)
    # 동시 실행으로 DB/로그/터널이 뒤섞이지 않게 OS 파일 잠금을 유지한다.
    args.runtime.mkdir(parents=True, exist_ok=True)
    with (args.runtime / 'supervisor.lock').open('a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0)
            lock.write(b'0')
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        # A stop request left while no supervisor was running must not stop the next launch.
        (args.runtime / 'stop.request').unlink(missing_ok=True)
        (args.runtime / 'connection.json').unlink(missing_ok=True)
        (args.runtime / '접속주소.txt').write_text('서버 연결 준비 중입니다. HTTPS 확인 후 새 주소가 표시됩니다.\n',encoding='utf-8')
        run(args.runtime, args.port)
