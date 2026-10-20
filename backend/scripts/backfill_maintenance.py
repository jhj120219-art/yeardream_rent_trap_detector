"""Backfill normalized maintenance rows from preserved listing JSON. Run offline after backup."""
import argparse
import json
import os
from backend.app.db import Store
from backend.app.maintenance_storage import project, read
from backend.app.advertised_costs import advertised_costs


def backfill(store):
    inserted = 0
    with store.connect() as db:
        rows=db.execute("SELECT id,owner,payload FROM objects WHERE kind='listing' ORDER BY id").fetchall()
        for row in rows:
            payload=json.loads(row['payload'])
            existing=read(db,row['id'],row['owner'])
            if existing is None:
                project(db,row['id'],payload)
                inserted += 1
            raw=payload.get('input',{})
            expected=advertised_costs(raw.get('options',{}),raw.get('confirmation',{}).get('user_confirmed',False))
            if read(db,row['id'],row['owner']) != expected:
                raise ValueError('Existing normalized maintenance differs from original JSON; nothing overwritten')
    return {'verified_listings':len(rows),'inserted_listings':inserted,'item_rows_per_listing':7}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline-confirmed',action='store_true')
    args=parser.parse_args()
    if not args.offline_confirmed:
        parser.error('Stop API and back up DB before passing --offline-confirmed')
    url=os.getenv('DATABASE_URL','')
    if not url:
        parser.error('DATABASE_URL is required')
    try:
        result=backfill(Store(database_url=url,initialize=False))
    except Exception:
        print('Backfill failed; transaction rolled back. Inspect schema and original data privately.')
        return 1
    print(json.dumps(result))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
