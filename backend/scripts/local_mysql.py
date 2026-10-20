"""Manage an explicitly provisioned private Windows MySQL runtime without a system service.
Provisioning metadata and credentials stay outside the repository. Never print credentials.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
import time

import pymysql


def configuration(runtime):
    runtime=runtime.resolve()
    metadata=json.loads((runtime/'installation.json').read_text(encoding='utf-8'))
    base=Path(metadata['base']).resolve()
    if not base.is_relative_to(runtime):
        raise ValueError('MySQL binaries must stay inside the private runtime')
    secret=json.loads((runtime/'credentials.json').read_text(encoding='utf-8'))
    return runtime,base,secret


def connect(runtime,secret):
    connection=pymysql.connect(host='127.0.0.1',port=3307,user='root',password=secret['root'],connect_timeout=3)
    with connection.cursor() as cursor:
        cursor.execute('SELECT @@datadir')
        actual=Path(cursor.fetchone()[0]).resolve()
    if actual!=(runtime/'data').resolve():
        connection.close()
        raise ValueError('Refusing to manage a different MySQL instance')
    return connection


def manage(action,runtime):
    runtime,base,secret=configuration(runtime)
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    if action=='start':
        try:
            connect(runtime,secret).close()
            print('Local MySQL already running.');return
        except pymysql.MySQLError:
            pass
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',3307))==0:
                raise RuntimeError('Port 3307 is occupied; refusing to start a duplicate database')
        process=subprocess.Popen([str(base/'bin/mysqld.exe'),'--defaults-file='+str(runtime/'mysql.ini')],
            cwd=runtime,creationflags=flags,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(60):
            if process.poll() is not None:raise RuntimeError('MySQL stopped; inspect private mysql.log')
            try:
                connect(runtime,secret).close();print('Local MySQL ready.');return
            except pymysql.MySQLError:time.sleep(1)
        raise RuntimeError('MySQL startup timed out')
    if action in ('status','stop'):
        with connect(runtime,secret) as connection,connection.cursor() as cursor:
            if action=='stop':cursor.execute('SHUTDOWN')
        print('Local MySQL '+('stopped safely.' if action=='stop' else 'ready.'));return
    # Password stays in a private client file, never process command lines.
    options=runtime/'backup-client.cnf'
    options.write_text('[client]\nuser=root\npassword='+secret['root']+'\nhost=127.0.0.1\nport=3307\n',encoding='utf-8')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination=runtime/'backups';destination.mkdir(exist_ok=True)
    connect(runtime,secret).close()
    try:
        for name in ('rent_app','rent_team'):
            target=destination/(name+'-'+stamp+'.sql')
            with target.open('xb') as output,(runtime/'backup-error.log').open('wb') as error:
                result=subprocess.run([str(base/'bin/mysqldump.exe'),'--defaults-extra-file='+str(options),
                    '--single-transaction','--no-tablespaces','--hex-blob','--set-gtid-purged=OFF',name],
                    stdout=output,stderr=error,creationflags=flags)
            if result.returncode or target.stat().st_size==0:
                raise RuntimeError('Backup failed; inspect private backup-error.log. Failed output is not a valid backup.')
        print('MySQL app/team SQL backups created in private runtime/backups.')
    finally:options.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('start','stop','status','backup'))
    parser.add_argument('--runtime',type=Path,required=True)
    args=parser.parse_args()
    try:manage(args.action,args.runtime)
    except Exception:
        print('Local MySQL operation failed. Check private runtime configuration/logs; credentials were not printed.')
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
