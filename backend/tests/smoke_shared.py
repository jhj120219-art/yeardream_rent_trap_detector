"""실제 HTTPS 팀 테스트 서버 검증. 가상 매물은 검사 후 세션과 함께 삭제한다."""
import argparse
import json
from pathlib import Path
import sqlite3
import os
import httpx
from backend.tests.test_backend import payload
from backend.scripts.team_server import backup


def smoke(runtime):
    info=json.loads((runtime/'connection.json').read_text(encoding='utf-8'))
    key=Path(info['key_file']).read_text(encoding='utf-8').strip()
    with httpx.Client(base_url=info['url'],timeout=45) as client:
        assert client.get('/health').status_code==401
        assert client.get('/openapi.json').status_code==401
        preflight=client.options('/sessions',headers={'Origin':'http://localhost:5173',
            'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'X-Team-Key,Authorization'})
        assert preflight.status_code==200
        client.headers['X-Team-Key']=key
        assert client.get('/ready').status_code==200
        capabilities=client.get('/capabilities').json()
        tokens=[]
        try:
            for _ in range(2):
                response=client.post('/sessions')
                assert response.status_code==201
                tokens.append(response.json()['token'])
            client.headers['Authorization']='Bearer '+tokens[0]
            saved=client.post('/listings',json=payload())
            assert saved.status_code==201,saved.text
            listing_id=saved.json()['id']
            result=client.post('/listings/'+listing_id+'/analyses')
            assert result.status_code==201,result.text
            analysis=result.json()
            assert client.get('/analyses/'+analysis['id']).json()==analysis
            report=client.get('/listings/'+listing_id+'/report').json()
            assert report['rent']['analysis_id']==analysis['id']
            assert report['maintenance']['state']=='ON_HOLD'
            client.headers['Authorization']='Bearer '+tokens[1]
            assert client.get('/listings/'+listing_id).status_code==404
            assert client.delete('/listings/'+listing_id).status_code==404
            client.headers['Authorization']='Bearer '+tokens[0]
            assert client.get('/maintenance/reference-cases').status_code==503
            assert client.delete('/listings/'+listing_id).status_code==204
            assert client.get('/analyses/'+analysis['id']).status_code==404
            print(json.dumps({'transport':'PUBLIC_HTTPS','data_status':capabilities['data_status'],
                'analysis_status':analysis['result']['status'],'maintenance':'ON_HOLD',
                'cross_session_access':'BLOCKED','cors':'PASS','synthetic_listing_deleted':True},ensure_ascii=False))
        finally:
            for token in tokens:
                client.headers['Authorization']='Bearer '+token
                assert client.delete('/sessions/current').status_code==204
    if info['database']=='mysql (DATABASE_URL)':
        from backend.app.db import Store
        if not os.getenv('DATABASE_URL'):
            raise RuntimeError('Set private DATABASE_URL to verify MySQL storage; SQLite backup is not applicable')
        store=Store(database_url=os.environ['DATABASE_URL'],initialize=False)
        assert store.available()
        print(json.dumps({'storage':'mysql','storage_ready':True,'backup':'Use local_mysql backup or deployment backup tooling'}))
        return
    target=backup(Path(info['database']),runtime/'backups')
    with sqlite3.connect(target) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()==('ok',)
        print(json.dumps({'backup_integrity':'ok','sessions':db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],
            'objects':db.execute('SELECT COUNT(*) FROM objects').fetchone()[0]}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--env-file',type=Path)
    args=parser.parse_args()
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file,override=True)
    smoke(args.runtime)
