import sqlite3
import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app
from backend.scripts.team_server import backup
from backend.tests.test_backend import payload


def test_shared_gate_cors_and_hold(tmp_path):
    key='x'*64
    path=tmp_path/'team.key'
    path.write_text(key)
    settings=Settings(db_path=tmp_path/'team.sqlite3',clean_csv=tmp_path/'missing.csv',
        shared_mode=True,team_key_file=str(path),maintenance_enabled=False)
    with TestClient(create_app(settings)) as client:
        for endpoint in ('/health','/openapi.json','/docs','/listings'):
            assert client.get(endpoint).status_code==401
        assert client.post('/sessions').status_code==401
        assert client.get('/health',headers={'X-Team-Key':'wrong'}).status_code==401
        preflight=client.options('/sessions',headers={'Origin':'http://localhost:5173',
            'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'X-Team-Key,Authorization'})
        assert preflight.status_code==200
        denied=client.get('/health',headers={'Origin':'http://localhost:5173'})
        assert denied.headers['access-control-allow-origin']=='http://localhost:5173'
        client.headers['X-Team-Key']=key
        assert client.get('/health').status_code==200
        assert client.get('/maintenance/reference-cases').status_code==503
        assert client.post('/listings/anything/utility-estimates',json={}).status_code==503
        assert client.get('/capabilities').json()['maintenance_enabled'] is False
        assert client.get('/listings').status_code==401
        token=client.post('/sessions').json()['token']
        client.headers['Authorization']='Bearer '+token
        assert client.get('/listings').json()['items']==[]
        saved=client.post('/listings',json=payload())
        assert saved.status_code==201
        report=client.get('/listings/'+saved.json()['id']+'/report').json()
        assert report['maintenance']=={'state':'ON_HOLD'}
        assert report['monthly_cost']=={'state':'ON_HOLD'}
        assert all('MAINTENANCE' not in action for action in report['workflow']['next_actions'])
        assert client.delete('/sessions/current').status_code==204
        assert client.get('/listings').status_code==401


def test_shared_configuration_fails_closed(tmp_path):
    with pytest.raises(ValueError):
        create_app(Settings(shared_mode=True,team_key_file=''))
    path=tmp_path/'key'
    path.write_text('short')
    with pytest.raises(ValueError):
        create_app(Settings(shared_mode=True,team_key_file=str(path)))


def test_online_backup_contains_committed_wal_data(tmp_path):
    db=tmp_path/'team.sqlite3'
    with sqlite3.connect(db) as connection:
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('CREATE TABLE example (value TEXT)')
        connection.execute("INSERT INTO example VALUES ('saved')")
        connection.commit()
        target=backup(db,tmp_path/'backups')
        with sqlite3.connect(target) as restored:
            assert restored.execute('SELECT value FROM example').fetchone()==('saved',)
            assert restored.execute('PRAGMA integrity_check').fetchone()==('ok',)
