"""가상 표본으로 실행한 HTTP 응답 예시. 운영 데이터·정확도 근거가 아니다.
저장소 루트: python -m backend.tests.export_examples
"""
import json
from pathlib import Path
import tempfile
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.config import Settings
from backend.tests.test_backend import raw_rows, payload
from backend.scripts.import_data import import_raw


def export():
    examples = {}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        raw, clean = root/'raw.csv', root/'clean.csv'
        raw_rows().to_csv(raw, index=False)
        import_raw(raw, clean)
        with TestClient(create_app(Settings(db_path=root/'app.sqlite3', clean_csv=clean))) as client:
            client.headers['Authorization'] = 'Bearer '+client.post('/sessions').json()['token']
            for name, changes in [
                ('COMPARED', {}), ('REFERENCE_ONLY', {'area_basis': 'SUPPLY'}),
                ('INSUFFICIENT_DATA', {'building_type': 'OFFICETEL'}),
                ('INPUT_REVIEW_REQUIRED', {}),
            ]:
                body = payload(**changes)
                if name == 'INPUT_REVIEW_REQUIRED':
                    body['confirmation']['user_confirmed'] = False
                saved = client.post('/listings', json=body)
                assert saved.status_code == 201
                response = client.post('/listings/'+saved.json()['id']+'/analyses')
                assert response.status_code == 201
                assert response.json()['result']['status'] == name
                examples[name] = dict(request=body, registration=saved.json(), http_status=response.status_code, response=response.json())
            bad = client.post('/listings', json=payload(floor=5.5))
            assert bad.status_code == 422
            examples['INVALID_INPUT'] = dict(http_status=422, response=bad.json())
            examples['CAPABILITIES'] = client.get('/capabilities').json()
        with TestClient(create_app(Settings(db_path=root/'missing.sqlite3', clean_csv=root/'missing.csv'))) as client:
            client.headers['Authorization'] = 'Bearer '+client.post('/sessions').json()['token']
            saved = client.post('/listings', json=payload()).json()
            response = client.post('/listings/'+saved['id']+'/analyses')
            assert response.status_code == 503
            examples['DATA_MISSING'] = dict(http_status=503, response=response.json())
    target = Path(__file__).resolve().parents[1]/'examples/api_responses.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps({'synthetic_only': True, 'examples': examples}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Exported 4 analysis states, input error, missing data and capabilities; synthetic only.')


if __name__ == '__main__':
    export()
