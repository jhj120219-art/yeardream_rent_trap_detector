"""Live checkbox contract and restart persistence check. Private state stays in runtime."""
import argparse
import json
from pathlib import Path
import httpx
from dotenv import dotenv_values
from backend.app.db import Store
from backend.app.advertised_costs import ITEMS
from backend.app.service_identity import public_identity
from backend.scripts.db_status import inspect
from backend.tests.test_backend import payload


def run(runtime, env_file, phase):
    info=json.loads((runtime/'connection.json').read_text(encoding='utf-8'))
    key=Path(info['key_file']).read_text(encoding='utf-8').strip()
    store=Store(database_url=dotenv_values(env_file)['DATABASE_URL'],initialize=False)
    state_file=runtime/'checkbox-verification-private.json'
    with httpx.Client(base_url=info['url'],timeout=45,headers={'X-Team-Key':key}) as c:
        for path in ('/health','/ready'):
            assert c.get(path).status_code==200
        cap=c.get('/capabilities').json()
        assert cap['service']==public_identity()
        assert cap['analysis_engine']=='v2' and cap['v2_status']=='READY'
        assert cap['same_building_first'] is False
        if phase=='prepare':
            assert not state_file.exists(), 'Previous verification must be resumed/cleaned first'
            state={'baseline':inspect(store),'tokens':[], 'listings':[]}
            def save():state_file.write_text(json.dumps(state),encoding='utf-8')
            save()
            try:
                for _ in range(2):
                    state['tokens'].append(c.post('/sessions').json()['token']);save()
                c.headers['Authorization']='Bearer '+state['tokens'][0]
                for total in (7,None,0):
                    body=payload(as_of='2026-10-21')
                    body['options']={'maintenance_input_mode':'CHECKBOX_TOTAL_V1','maintenance_10k_krw':total,
                        **{field:('INCLUDED' if item in ('WATER','INTERNET') else 'UNKNOWN') for item,(field,_) in ITEMS.items()}}
                    response=c.post('/listings',json=body);assert response.status_code==201
                    state['listings'].append(response.json()['id']);save()
                    report=c.get('/listings/'+state['listings'][-1]+'/report').json()
                    groups=report['maintenance_reference_groups']
                    assert groups['state']=='REFERENCE_NOT_CONNECTED'
                    assert groups['advertised_selected_total_10k_krw']==total
                    assert {r['item'] for r in groups['selected']['items']}=={'WATER','INTERNET'}
                    assert {r['item'] for r in groups['unselected']['items']}=={'ELECTRICITY','GAS','OTHER'}
                    for name in ('selected','unselected'):
                        assert groups[name]['reference_low_total_krw'] is None
                        assert all(row['reference_low_krw'] is None for row in groups[name]['items'])
                    assert report['advertised_costs']['category_version']=='FIVE_ITEMS_V1'
                    assert len(report['advertised_costs']['items'])==5
                    assert report['service']==public_identity()
                response=c.post('/listings/'+state['listings'][0]+'/analyses')
                assert response.status_code==201
                assert response.json()['result']['status']=='COMPARED'
                state['analysis']=response.json();save()
                body['confirmation']['user_confirmed']=False
                response=c.post('/listings',json=body);assert response.status_code==201
                state['listings'].append(response.json()['id']);save()
                response=c.post('/listings/'+state['listings'][-1]+'/analyses')
                assert response.json()['result']['status']=='INPUT_REVIEW_REQUIRED'
                state['after_save']=inspect(store);save()
                with store.connect() as db:
                    for lid in state['listings']:
                        rows=db.execute('SELECT item,status,amount_10k_krw FROM listing_maintenance_items WHERE listing_id=?',(lid,)).fetchall()
                        assert len(rows)==5
                        assert all(row['amount_10k_krw'] is None for row in rows)
                print(json.dumps({'phase':'PREPARED','before':state['baseline'],'after':state['after_save'],
                    'identity_and_five_items':'PASS','null_vs_zero':'PASS','unconfirmed_price_calculation':'BLOCKED',
                    'reference_costs':'NOT_CONNECTED_NULL'},ensure_ascii=False))
            except Exception:
                for token in state['tokens']:
                    c.headers['Authorization']='Bearer '+token;c.delete('/sessions/current')
                state_file.unlink(missing_ok=True)
                raise
        else:
            state=json.loads(state_file.read_text(encoding='utf-8'))
            try:
                c.headers['Authorization']='Bearer '+state['tokens'][0]
                for lid in state['listings']:
                    assert c.get('/listings/'+lid).status_code==200
                    assert c.get('/listings/'+lid+'/report').status_code==200
                report=c.get('/listings/'+state['listings'][0]+'/report').json()
                assert report['rent']['result']==state['analysis']['result']
                c.headers['Authorization']='Bearer '+state['tokens'][1]
                assert c.get('/listings/'+state['listings'][0]+'/report').status_code==404
                assert inspect(store)==state['after_save']
                print(json.dumps({'phase':'AFTER_RESTART','persistence':'PASS','owner_isolation':'PASS',
                    'rows_unchanged':True,'url':info['url']},ensure_ascii=False))
            finally:
                for token in state['tokens']:
                    c.headers['Authorization']='Bearer '+token
                    assert c.delete('/sessions/current').status_code==204
                assert inspect(store)==state['baseline']
                state_file.unlink()
                print(json.dumps({'cleanup':'ONLY_OWN_TEST_SESSIONS','after':inspect(store)},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('prepare','resume'));p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--env-file',type=Path,required=True);a=p.parse_args()
    run(a.runtime,a.env_file,a.phase)
