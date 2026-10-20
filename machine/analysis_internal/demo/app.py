# -*- coding: utf-8 -*-
"""로컬 시연 서버: 입력값을 받아 engine_v2(현재 정책 v2)로 분석한다. 표준 라이브러리 http.server 만 사용, 127.0.0.1 에서만 열린다.
- 설계 6개 구(강서·관악·광진·노원·동작·마포)의 신규 월세 실거래만 비교군으로 쓴다. 다른 구는 '범위 밖'.
- 지번(본번·부번)을 넣으면 0단계를 시도한다. 건물 동수는 캐시(data/lot_buildings_cache.csv)에 있거나, 건축HUB 키 파일이 있으면 즉시 조회한다.
  키는 서버 안에서만 쓰고 화면·로그에 나오지 않는다.
실행: python app.py  (또는 실행.bat)   종료: Ctrl+C
"""
import json
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import ROOT, np, pd, load_policy, load_rent, load_building_cache
from engine_v2 import EngineV2

HERE = Path(__file__).resolve().parent
PORT = 8765
KEY_FILE = ROOT.parent / '공공데이터포털 인증키(건축물대장).txt'     # 저장소 밖의 로컬 키 파일(없으면 캐시만 사용)
HUB = 'http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo'

print('데이터와 엔진을 불러오는 중...', flush=True)
policy = load_policy()
rent_df = load_rent(ROOT / 'output' / 'clean_rent_data.csv')
cache = load_building_cache(ROOT / policy['stage0']['building_cache'])
eng = EngineV2(rent_df, cache, policy)
AS_OF = rent_df['date'].max() + pd.Timedelta(days=1)
codes = rent_df.drop_duplicates(['gu', 'dong'])[['gu', 'dong', 'CGG_CD', 'STDG_CD']]
CODE = {(g, d): (c, s) for g, d, c, s in zip(codes.gu, codes.dong, codes.CGG_CD, codes.STDG_CD)}
META = {g: sorted(x['dong']) for g, x in codes.groupby('gu')}
KEY = None
if KEY_FILE.exists():
    m = re.findall(r'[A-Za-z0-9%+=/]{40,}', KEY_FILE.read_text(encoding='utf-8'))
    KEY = m[0] if m else None
LOCK = threading.Lock()
print(f'준비 완료: 비교 데이터 기준일 {AS_OF.date()}, 구 {len(META)}개, 건축HUB 즉시 조회 {"가능" if KEY else "불가(캐시만)"}', flush=True)


def lookup_building(cgg, stdg, mno, sno):
    """캐시 -> 없으면 건축HUB 조회(키가 있을 때). 반환: 주건축물 수 또는 None(확인 불가)."""
    k = (cgg, stdg, mno, sno)
    if k in eng.cache:
        return eng.cache[k]
    if not KEY:
        return None
    import requests
    try:
        r = requests.get(HUB, params={'serviceKey': unquote(KEY), 'sigunguCd': cgg, 'bjdongCd': stdg, 'platGbCd': '0', 'bun': mno, 'ji': sno,
                                      'numOfRows': 100, 'pageNo': 1, '_type': 'json'}, timeout=15)
        body = r.json()['response']['body']
        it = (body.get('items') or {})
        it = it.get('item') if isinstance(it, dict) else None
        items = [] if it is None else (it if isinstance(it, list) else [it])
        n = len([x for x in items if str(x.get('mainAtchGbCd')) == '0'])
        eng.cache[k] = n
        return n
    except Exception:
        return None


def num(v, name, lo, hi):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f'{name}을(를) 숫자로 입력해 주세요.')
    if not (lo <= x <= hi):
        raise ValueError(f'{name} 값이 범위({lo}~{hi})를 벗어났습니다.')
    return x


def analyze(p: dict) -> dict:
    gu, dong, usage = p.get('gu'), p.get('dong'), p.get('usage')
    if gu not in META:
        return dict(status='OUT_OF_SCOPE', message='이 시연은 강서·관악·광진·노원·동작·마포구의 데이터만 가지고 있습니다.')
    if (gu, dong) not in CODE:
        return dict(status='INPUT_REVIEW_REQUIRED', message='동 이름을 목록에서 선택해 주세요.')
    if usage not in ('아파트', '연립다세대', '오피스텔', '단독다가구'):
        return dict(status='INPUT_REVIEW_REQUIRED', message='건물 유형을 선택해 주세요.')
    area = num(p.get('area'), '면적(㎡)', 5, 200)
    dep = num(p.get('dep'), '보증금(만원)', 0, 1000000)
    rentv = num(p.get('rent'), '월세(만원)', 0.1, 100000)
    arch = None
    if str(p.get('arch', '')).strip():
        arch = num(p.get('arch'), '준공연도', 1950, 2030)
    notes = []
    if p.get('area_basis') == '공급':
        return dict(status='REFERENCE_ONLY', label='UNRATED', reason='AREA_BASIS_SUPPLY',
                    message='공급(계약)면적으로는 전용면적 기준 거래와 정확히 비교할 수 없어 판정하지 않습니다. 전용면적을 입력해 주세요.' if usage != '단독다가구' else '단독다가구는 계약면적 기준으로 비교합니다.')
    floor_type = p.get('floor_type', 'UNKNOWN')       # GROUND(지상 확인) / BASEMENT / UNKNOWN
    basement = floor_type == 'BASEMENT'
    cgg, stdg = CODE[(gu, dong)]
    mno = sno = np.nan
    mm, ss = str(p.get('main_no', '')).strip(), str(p.get('sub_no', '')).strip()
    if mm:
        if not mm.isdigit() or (ss and not ss.isdigit()):
            return dict(status='INPUT_REVIEW_REQUIRED', message='지번은 숫자로 입력해 주세요. (예: 본번 279, 부번 235)')
        mno, sno = mm.zfill(4), (ss or '0').zfill(4)
    row = dict(gu=gu, dong=dong, usage=usage, area=area, dep=dep, rent=rentv, arch=np.nan if arch is None else arch, basement=basement,
               date=AS_OF, CGG_CD=cgg, STDG_CD=stdg, MNO=mno, SNO=sno)
    if isinstance(mno, str):
        lookup_building(cgg, stdg, mno, sno)          # 캐시에 없으면 건축HUB 조회 결과를 엔진 캐시에 반영
    with LOCK:
        rec = eng.evaluate(row, as_of=AS_OF)
    if rec['source'] == 'NONE':
        return dict(status='INSUFFICIENT_DATA', label='UNRATED', reason='NO_COMPARABLES',
                    message='조건을 넓혀도 비교할 신규 계약이 부족해 가격 판정을 보류합니다.', stage0_reason=rec['stage0_reason'])
    prob = eng.trust_prob(rec)
    grade = eng.grade(prob)
    label, reason = eng.label(rentv, rec, grade)
    ratio = rentv / rec['pred']
    check = (rentv < 3 or rentv > 500 or ratio > 2.5 or ratio < 0.4)
    if usage == '단독다가구':
        if floor_type == 'BASEMENT':
            label, reason = 'UNRATED', 'BASEMENT_LISTING'
        elif floor_type != 'GROUND':
            label, reason = 'UNRATED', 'FLOOR_UNCONFIRMED'
            notes.append('단독다가구는 지상층임을 확인해야 가격 판정을 합니다. (반지하 여부는 거래 데이터에서 알 수 없음)')
    if check:
        label, reason = 'UNRATED', 'INPUT_CHECK'
    return dict(status='COMPARED' if label != 'UNRATED' else ('INPUT_REVIEW_REQUIRED' if check else 'REFERENCE_ONLY'), label=label, reason=reason,
                grade=grade, p=round(prob, 3), source=rec['source'], stage=int(rec['stage_new']), n=int(rec['n_use']),
                pred=round(rec['pred'], 1), q10=round(rec['q10'], 1), q25=round(rec['q25'], 1), q75=round(rec['q75'], 1), q90=round(rec['q90'], 1),
                rent=rentv, stage0_reason=rec['stage0_reason'], as_of=str(AS_OF.date()), notes=notes)


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self._send(200, (HERE / 'index.html').read_bytes(), 'text/html; charset=utf-8')
        elif self.path == '/meta':
            self._send(200, json.dumps(META, ensure_ascii=False), 'application/json; charset=utf-8')
        else:
            self._send(404, 'not found', 'text/plain')

    def do_POST(self):
        if self.path != '/analyze':
            return self._send(404, 'not found', 'text/plain')
        try:
            n = int(self.headers.get('Content-Length', 0))
            res = analyze(json.loads(self.rfile.read(n).decode('utf-8')))
        except ValueError as e:
            res = dict(status='INPUT_REVIEW_REQUIRED', message=str(e))
        except Exception as e:
            res = dict(status='ERROR', message='분석 중 오류가 발생했습니다.')
            print('오류:', type(e).__name__, e, flush=True)
        self._send(200, json.dumps(res, ensure_ascii=False, default=lambda o: None), 'application/json; charset=utf-8')

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), H)
    url = f'http://127.0.0.1:{PORT}/'
    print('시연 페이지:', url, '(종료: Ctrl+C)', flush=True)
    if '--no-browser' not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
