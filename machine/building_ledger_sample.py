#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""건축물대장 표제부(건축HUB)로 단독다가구 지번의 지하층 유무를 표본 확인한다.

필요한 것: 공공데이터포털 인증키(건축HUB_건축물대장정보 서비스 활용신청 승인 후).
  키는 환경변수 DATA_GO_KR_KEY 또는 --key-file(txt, 20자 이상 영숫자·%·= 첫 토큰)로 전달. 화면·파일에 출력하지 않는다.
사용: python building_ledger_sample.py --n 200            # 표본 200개 지번
      python building_ledger_sample.py --selftest         # 키 없이 파싱·분류 로직만 검사
엔드포인트(PublicDataReader 소스에서 확인): http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo
요청: serviceKey, sigunguCd(5), bjdongCd(5), platGbCd(0), bun(4), ji(4), numOfRows, pageNo, _type=json
분류: NO_BASEMENT(주건축물 1동, 지하층수 0) / HAS_BASEMENT / MULTIPLE_BUILDINGS(주건축물 2동 이상) / UNKNOWN(조회 결과 없음)
"""
import argparse, os, re, sys, time, json
from pathlib import Path
from urllib.parse import unquote
import requests
import pandas as pd

HERE = Path(__file__).parent
URL = 'http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo'


def parse_items(payload):
    """API JSON -> 건물 dict 목록 (item 이 없음/단건/다건 모두 처리)"""
    try:
        items = payload['response']['body']['items']
    except (KeyError, TypeError):
        return []
    if not items:
        return []
    it = items.get('item') if isinstance(items, dict) else items
    if it is None:
        return []
    return it if isinstance(it, list) else [it]


def _i(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def classify(items):
    if not items:
        return 'UNKNOWN', {}
    main = [b for b in items if str(b.get('mainAtchGbCd', '0')) in ('0', '', 'None')] or items
    info = dict(n_buildings=len(main), grnd=[_i(b.get('grndFlrCnt')) for b in main], ugrnd=[_i(b.get('ugrndFlrCnt')) for b in main],
                purpose=[b.get('mainPurpsCdNm') for b in main], name=[b.get('bldNm') for b in main])
    if len(main) >= 2:
        return 'MULTIPLE_BUILDINGS', info
    u = info['ugrnd'][0]
    if u is None:
        return 'UNKNOWN', info
    return ('NO_BASEMENT' if u == 0 else 'HAS_BASEMENT'), info


def fetch(key, sigungu, bjdong, bun, ji, session=None):
    params = {'serviceKey': unquote(key), 'sigunguCd': sigungu, 'bjdongCd': bjdong, 'platGbCd': '0',
              'bun': str(bun).zfill(4), 'ji': str(ji).zfill(4), 'numOfRows': 100, 'pageNo': 1, '_type': 'json'}
    r = (session or requests).get(URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def selftest():
    one = {'response': {'body': {'items': {'item': {'mainAtchGbCd': '0', 'grndFlrCnt': '3', 'ugrndFlrCnt': '0', 'mainPurpsCdNm': '다가구주택', 'bldNm': ''}}}}}
    assert classify(parse_items(one))[0] == 'NO_BASEMENT'
    two = {'response': {'body': {'items': {'item': [{'mainAtchGbCd': '0', 'grndFlrCnt': '4', 'ugrndFlrCnt': '1'},
                                                     {'mainAtchGbCd': '1', 'grndFlrCnt': '1', 'ugrndFlrCnt': '0'}]}}}}
    assert classify(parse_items(two))[0] == 'HAS_BASEMENT'            # 부속건물(1)은 제외하고 주건축물만 본다
    many = {'response': {'body': {'items': {'item': [{'mainAtchGbCd': '0', 'ugrndFlrCnt': '0'}, {'mainAtchGbCd': '0', 'ugrndFlrCnt': '1'}]}}}}
    assert classify(parse_items(many))[0] == 'MULTIPLE_BUILDINGS'
    assert classify(parse_items({'response': {'body': {'items': ''}}}))[0] == 'UNKNOWN'
    assert classify(parse_items({'response': {'header': {'resultCode': '30'}}}))[0] == 'UNKNOWN'
    print('selftest ok')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=200); ap.add_argument('--key-file'); ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--sleep', type=float, default=0.2)
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    key = os.environ.get('DATA_GO_KR_KEY')
    if not key and a.key_file:
        key = re.findall(r'[A-Za-z0-9%+=/]{20,}', Path(a.key_file).read_text(encoding='utf-8'))[0]
    if not key:
        sys.exit('인증키가 필요합니다(DATA_GO_KR_KEY 또는 --key-file).')
    r = pd.read_csv(HERE / 'output' / 'clean_rent_data.csv', dtype={'CGG_CD': str, 'STDG_CD': str, 'MNO': str, 'SNO': str}, low_memory=False)
    d = r[(r['usage'] == '단독다가구') & r['is_new']].copy()
    d['lot'] = d['CGG_CD'] + '|' + d['STDG_CD'] + '|' + d['MNO'].str.zfill(4) + '|' + d['SNO'].str.zfill(4)
    lots = d.groupby('lot').agg(gu=('gu', 'first'), dong=('dong', 'first'), contracts=('rent', 'size')).reset_index()
    per_gu = max(1, a.n // lots['gu'].nunique())
    sample = pd.concat([g.sample(min(per_gu, len(g)), random_state=7) for _, g in lots.groupby('gu')])
    rows, sess = [], requests.Session()
    for row in sample.itertuples():
        cgg, stdg, bun, ji = row.lot.split('|')
        try:
            items = parse_items(fetch(key, cgg, stdg, bun, ji, sess))
            cls, info = classify(items)
        except Exception as e:                                   # 키·네트워크 오류 메시지에 키가 섞이지 않게 형식만 기록
            cls, info = 'ERROR', {'error': type(e).__name__}
        rows.append(dict(lot=row.lot, gu=row.gu, dong=row.dong, contracts=row.contracts, cls=cls, **{k: str(v) for k, v in info.items()}))
        time.sleep(a.sleep)
    out = pd.DataFrame(rows)
    (HERE / 'output').mkdir(exist_ok=True)
    out.to_csv(HERE / 'output' / 'ledger_sample.csv', index=False, encoding='utf-8-sig')
    print(out['cls'].value_counts().to_string())
    ok = out[out['cls'].isin(['NO_BASEMENT', 'HAS_BASEMENT', 'MULTIPLE_BUILDINGS'])]
    print('조회 성공률: %.1f%%' % (100 * len(ok) / len(out)))
    if len(ok):
        w = ok['contracts']
        print('지하층이 있는 지번 비율: 지번 기준 %.1f%%, 계약 수 가중 %.1f%%' % (
            100 * (ok['cls'] == 'HAS_BASEMENT').mean(), 100 * (w[ok['cls'] == 'HAS_BASEMENT'].sum() / w.sum())))


if __name__ == '__main__':
    main()
