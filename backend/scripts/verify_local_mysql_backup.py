"""Restore a local SQL backup into a newly named inspection DB; never overwrite an existing DB."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid
from backend.scripts.local_mysql import configuration, connect

TABLES = ('sessions','objects','object_links','listing_maintenance','listing_maintenance_items')


def fingerprint(connection, database):
    result = {}
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f'SELECT * FROM `{database}`.`{table}`')
            rows = sorted(repr(row) for row in cursor.fetchall())
            result[table] = {'rows': len(rows), 'sha256': hashlib.sha256(
                '\n'.join(rows).encode('utf-8')).hexdigest()}
    return result


def verify(runtime, source, backup):
    if source not in ('rent_app','rent_team'):
        raise ValueError('Unsupported source')
    runtime, base, secret = configuration(runtime)
    backup = backup.resolve()
    if not backup.is_relative_to((runtime/'backups').resolve()) or not backup.name.startswith(source+'-'):
        raise ValueError('Only private local backups are accepted')
    # local_mysql creates single-database dumps without database switching commands.
    sql = backup.read_bytes()
    if not sql or re.search(rb'^\s*(?:USE\s|CREATE\s+DATABASE\s|DROP\s+DATABASE\s)', sql, re.I|re.M):
        raise ValueError('Unsafe or empty dump')
    target = 'rent_restore_check_' + uuid.uuid4().hex
    options = runtime / (target+'.cnf')
    created = False
    with connect(runtime, secret) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f'CREATE DATABASE `{target}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
            created = True
            options.write_text('[client]\nuser=root\npassword='+secret['root']+
                               '\nhost=127.0.0.1\nport=3307\n', encoding='utf-8')
            with backup.open('rb') as source_file:
                process = subprocess.run([str(base/'bin/mysql.exe'),'--defaults-extra-file='+str(options),
                    '--database='+target], stdin=source_file, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if process.returncode:
                raise RuntimeError('Restore failed')
            before = fingerprint(connection, source)
            restored = fingerprint(connection, target)
            if restored != before:
                raise ValueError('Restored snapshot differs from current source; source may have changed during backup')
            return {'source':source,'restored_rows':{name:value['rows'] for name,value in restored.items()},
                    'all_table_values_match':True,'backup_sha256':hashlib.sha256(sql).hexdigest(),
                    'source_modified':False,'temporary_database_removed':True}
        finally:
            options.unlink(missing_ok=True)
            if created:
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP DATABASE `{target}`')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--source',choices=('rent_app','rent_team'),required=True)
    parser.add_argument('--backup',type=Path,required=True)
    args=parser.parse_args()
    try:
        print(json.dumps(verify(args.runtime,args.source,args.backup)))
    except Exception:
        print('Backup verification failed; no source database was overwritten. Check private configuration and backup freshness.')
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
