"""Read-only deployment checks. Never prints URLs, credentials, input rows or exceptions."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from backend.app.config import Settings
from backend.app.db import mysql_options
from backend.scripts.migrate_mysql import TABLES


def result(name, passed, message):
    return {'check': name, 'status': 'ok' if passed else 'failed', 'message': message}


def valid_origin(origin):
    parsed = urlsplit(origin)
    port = parsed.port
    return (port in (None, 443) and parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username
            and not parsed.password and parsed.path in ('', '/') and not parsed.query
            and not parsed.fragment and '*' not in origin
            and parsed.hostname not in ('localhost', '127.0.0.1', 'example.com', 'frontend.example.com'))


def check_configuration(settings):
    checks = []
    try:
        options = mysql_options(settings.database_url)
        configured = bool(options['password']) and options['password'] not in ('CHANGE_ME', 'change-me')
    except (ValueError, TypeError):
        configured = False
    checks.append(result('mysql_url', configured, 'A MySQL URL with a real password is required.'))
    checks.append(result('schema_initialization', not settings.db_auto_init, 'Set DB_AUTO_INIT=false; initialize schema separately.'))
    checks.append(result('access_protection', settings.shared_mode, 'TEAM_SHARED_MODE=true is required for this team deployment.'))
    try:
        key = Path(settings.team_key_file).read_text(encoding='utf-8').strip() if settings.team_key_file else ''
        valid_key = len(key) >= 40 and key.isascii()
    except (OSError, UnicodeError, ValueError):
        valid_key = False
    checks.append(result('team_key', valid_key, 'A readable private ASCII team key of at least 40 characters is required.'))
    try:
        origins_ok = bool(settings.cors_origins) and all(valid_origin(origin) for origin in settings.cors_origins)
    except ValueError:
        origins_ok = False
    checks.append(result('frontend_origins', origins_ok, 'Set explicit HTTPS frontend origins.'))
    checks.append(result('maintenance_hold', not settings.maintenance_enabled, 'Keep MAINTENANCE_ENABLED=false until analyst review.'))
    try:
        from backend.app.analysis_service import load_pool
        load_pool(settings.clean_csv)
        data_ok = True
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        data_ok = False
    checks.append(result('analysis_data', data_ok, 'A readable, valid clean transaction CSV is required.'))
    return checks


def check_database(url, allow_private_network=False):
    import pymysql
    connection = None
    try:
        options = mysql_options(url)
        options.update(connect_timeout=5, read_timeout=5, write_timeout=5)
        connection = pymysql.connect(**options, cursorclass=pymysql.cursors.DictCursor)
        with connection.cursor() as cursor:
            cursor.execute('START TRANSACTION READ ONLY')
            cursor.execute('SELECT @@version AS version, @@version_comment AS comment')
            info = cursor.fetchone()
            mysql8 = info['version'].startswith('8.') and 'mariadb' not in (info['version'] + info['comment']).lower()
            cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
            cipher = cursor.fetchone()
            tls = bool(cipher and cipher['Value'])
            verified_tls = tls and options.get('ssl_verify_cert', False) and options.get('ssl_verify_identity', False)
            cursor.execute("SELECT TABLE_NAME AS name, ENGINE AS engine FROM information_schema.TABLES "
                           "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('sessions','objects','object_links')")
            engines = {row['name']: row['engine'] for row in cursor.fetchall()}
            schema_ok = all(engines.get(table) == 'InnoDB' for table in TABLES)
            for table, columns in TABLES.items():
                cursor.execute('SELECT ' + ','.join(columns) + ' FROM ' + table + ' LIMIT 0')
        return [result('database_connection', True, 'Connected using read-only checks.'),
                result('mysql_version', mysql8, 'MySQL 8.x is required.'),
                result('database_transport', verified_tls or allow_private_network,
                       'Certificate-verified TLS required unless a trusted private network was explicitly selected.'),
                result('database_schema', schema_ok, 'All storage tables and columns must exist and use InnoDB.')]
    except (pymysql.MySQLError, OSError, ValueError, TypeError, KeyError):
        return [result('database_connection', False,
                       'Connection or schema check failed. Check private server settings; no database changes were made.')]
    finally:
        if connection is not None:
            try:
                connection.rollback()
            except (pymysql.MySQLError, OSError):
                pass
            try:
                connection.close()
            except (pymysql.MySQLError, OSError):
                pass


def run(settings, no_connect=False, allow_private_network=False):
    checks = check_configuration(settings)
    if not no_connect and checks[0]['status'] == 'ok':
        checks.extend(check_database(settings.database_url, allow_private_network))
    failed = any(item['status'] == 'failed' for item in checks)
    status = 'blocked' if failed else ('incomplete' if no_connect else 'ready_for_start')
    return {'status': status, 'checks': checks}, (1 if failed else 2 if no_connect else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--no-connect', action='store_true', help='Configuration only; never reports ready')
    parser.add_argument('--allow-private-network', action='store_true', help='Explicitly allow plaintext on a trusted private DB network')
    args = parser.parse_args()
    if args.env_file:
        from dotenv import load_dotenv
        if not args.env_file.is_file():
            print(json.dumps({'status': 'blocked', 'reason': 'Environment file is missing.'}))
            return 1
        load_dotenv(args.env_file, override=False)
    report, code = run(Settings(), args.no_connect, args.allow_private_network)
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
