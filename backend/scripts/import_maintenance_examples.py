"""Import frontend output examples into a clearly separated rent_examples* database only."""
import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path
from uuid import uuid4
from backend.app.db import Store, digest, now
from backend.app.schemas import ListingInput
from backend.app.analysis_service import review
from backend.app.maintenance_storage import project


def import_examples(store, paths):
    if not store.mysql or not store.options['database'].startswith('rent_examples'):
        raise ValueError('Synthetic output examples require a separate rent_examples database')
    sources=[]; records=[]
    for path in paths:
        path=Path(path)
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        if data.get('synthetic_only') is not True and data.get('synthetic_inputs_only') is not True:
            raise ValueError('Input must explicitly identify synthetic examples')
        sources.append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'original':data})
        for name,example in data['examples'].items():
            registration=example.get('registration')
            raw=registration.get('input') if registration else example.get('synthetic_listing')
            if raw is None:continue
            ListingInput.model_validate(raw)
            records.append({'input':raw,'validation':registration.get('validation') if registration else review(raw),
                            'sample_source':{'file':path.name,'example':name,'synthetic':True}})
    owner=str(uuid4());date=now()
    with store.connect() as db:
        if db.execute('SELECT COUNT(*) AS total FROM sessions').fetchone()['total']:
            raise ValueError('Example database is not empty; refusing duplicate import')
        db.execute('INSERT INTO sessions VALUES(?,?,?)',(owner,digest(secrets.token_urlsafe(32)),date))
        for source in sources:
            db.execute('INSERT INTO objects VALUES(?,?,?,?,?,?)',
                       (str(uuid4()),owner,'synthetic_import_source',None,json.dumps(source,ensure_ascii=False,allow_nan=False),date))
        for payload in records:
            oid=str(uuid4())
            db.execute('INSERT INTO objects VALUES(?,?,?,?,?,?)',
                       (oid,owner,'listing',None,json.dumps(payload,ensure_ascii=False,allow_nan=False),date))
            project(db,oid,payload)
    return {'database_role':'SYNTHETIC_EXAMPLES_ONLY','sources':len(sources),'maintenance_rows':len(records),
            'maintenance_item_rows':len(records)*7,'team_database_modified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,action='append',required=True)
    args=parser.parse_args()
    try:
        store=Store(database_url=os.getenv('DATABASE_URL',''),initialize=False)
        print(json.dumps(import_examples(store,args.input)))
    except Exception:
        print('Import failed; no overwrite permitted. Check private configuration, source flags and empty example database.')
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
