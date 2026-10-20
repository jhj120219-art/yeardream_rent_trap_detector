"""Public HTTPS contract checks for the supplied frontend preview; no keys enter that site."""
import argparse
import json
from pathlib import Path
import httpx
from backend.tests.test_backend import payload

ORIGIN='https://munhwadream-rent-preview.zxaq3166.chatgpt.site'


def smoke(runtime):
    info=json.loads((runtime/'connection.json').read_text(encoding='utf-8'))
    key=Path(info['key_file']).read_text(encoding='utf-8').strip()
    with httpx.Client(base_url=info['url'],timeout=45) as client:
        preflight=client.options('/locations',headers={'Origin':ORIGIN,
            'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'x-team-key,authorization'})
        assert preflight.status_code==200
        assert preflight.headers['access-control-allow-origin']==ORIGIN
        denied=client.get('/locations',headers={'Origin':ORIGIN})
        assert denied.status_code==401
        assert denied.headers['access-control-allow-origin']==ORIGIN
        bad=client.options('/locations',headers={'Origin':'https://unapproved.example',
            'Access-Control-Request-Method':'GET'})
        assert bad.status_code==400
        client.headers.update({'X-Team-Key':key,'Origin':ORIGIN})
        catalog=client.get('/locations').json()
        assert catalog['districts']
        district=client.get('/locations?district_code=11620').json()['districts'][0]
        assert any(x['dong_name']=='봉천동' for x in district['dongs'])
        assert client.get('/locations?district_code=11110').status_code==404
        token=client.post('/sessions').json()['token']
        client.headers['Authorization']='Bearer '+token
        try:
            body=payload(as_of='2026-10-20')
            body['listing'].pop('legal_dong_code')
            body['listing'].update(dong='봉천동',address_text=None,unit_ho=None)
            saved=client.post('/listings',json=body)
            assert saved.status_code==201,saved.text
            lid=saved.json()['id']
            result=client.post('/listings/'+lid+'/analyses')
            assert result.status_code==201
            assert result.json()['result']['status']=='COMPARED'
            report=client.get('/listings/'+lid+'/report').json()
            assert report['rent']['result']==result.json()['result']
            assert report['maintenance']['state']=='ON_HOLD'
            print(json.dumps({'transport':'PUBLIC_HTTPS','origin_preflight':'PASS',
                'unapproved_origin':'REJECTED','missing_key':401,'districts':len(catalog['districts']),
                'legal_dongs':sum(len(x['dongs']) for x in catalog['districts']),
                'data_as_of':catalog['data_as_of'],'dong_name_input':'COMPARED','report':'PASS',
                'maintenance':'ON_HOLD'},ensure_ascii=False))
        finally:
            assert client.delete('/sessions/current').status_code==204


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',type=Path,required=True)
    smoke(parser.parse_args().runtime)
