"""Local/SSH-only aggregate DB inspection. No HTTP route or raw user data output."""
import argparse
import json
from pathlib import Path
from backend.app.config import Settings
from backend.app.db import Store


def inspect(store):
    if not store.available():
        raise ValueError('Database or required schema is unavailable')
    with store.connect() as db:
        def count(table):
            return db.execute('SELECT COUNT(*) AS total FROM '+table).fetchone()['total']
        objects={row['kind']:row['total'] for row in db.execute(
            'SELECT kind,COUNT(*) AS total FROM objects GROUP BY kind').fetchall()}
        groups=db.execute('SELECT item_count,COUNT(*) AS listing_count FROM '
            '(SELECT m.listing_id,COUNT(i.item) AS item_count FROM listing_maintenance m '
            'LEFT JOIN listing_maintenance_items i ON i.listing_id=m.listing_id '
            'GROUP BY m.listing_id) AS counts GROUP BY item_count').fetchall()
        missing=db.execute("SELECT COUNT(*) AS total FROM objects o LEFT JOIN listing_maintenance m "
            "ON m.listing_id=o.id WHERE o.kind='listing' AND m.listing_id IS NULL").fetchone()['total']
        return {'status':'READY','storage':'MYSQL' if store.mysql else 'EXPLICIT_SQLITE',
            'sessions':count('sessions'),'objects_by_kind':objects,
            'maintenance_total_rows':count('listing_maintenance'),
            'maintenance_item_rows':count('listing_maintenance_items'),
            'listings_by_item_count':{str(row['item_count']):row['listing_count'] for row in groups},
            'listings_without_maintenance_row':missing,
            'raw_user_data_included':False,'changes_performed':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path)
    args=parser.parse_args()
    try:
        if args.env_file:
            if not args.env_file.is_file():raise ValueError('Missing environment file')
            from dotenv import load_dotenv
            load_dotenv(args.env_file,override=True)
        settings=Settings()
        result=inspect(Store(settings.db_path,database_url=settings.database_url,initialize=False))
    except Exception:
        print(json.dumps({'status':'UNAVAILABLE','reason':'Check private DB configuration and schema; no changes performed.'}))
        return 1
    print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
