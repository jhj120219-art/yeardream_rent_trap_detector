# -*- coding: utf-8 -*-
"""관리비 점검 로컬 데모 서버(127.0.0.1:8766). 표준 라이브러리만 사용.
POST /estimate : 조건(월·가구원수·주택유형·면적·난방·광고 관리비/포함 항목)을 받아 항목별 서울 참고 월 요금(범위)과 확인 질문을 돌려준다.
POST /parse    : 광고 문구 텍스트를 규칙 파서로 구조화(이미지 전사 결과를 붙여 넣는 용도).
실행: python app.py  (또는 실행.bat)"""
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'extraction'))
try:      # 패키지로 불러온 경우(integration.run_maintenance, 백엔드): 같은 모듈을 공유한다(두 벌 로드되어 캐시·설정이 갈라지는 것을 막음)
    from .. import reference as R
    from .. import micro_ref
    from ..calc import electricity_bill, gas_bill, water_bill
    from ..check import assess, INTERNET_RANGE
    from ..tariffs import ELECTRIC, GAS, WATER
except ImportError:      # 직접 실행(python app.py)이나 시험에서 `from app import ...` 로 불러온 경우
    sys.path.insert(0, str(HERE.parents[1]))                 # analysis_internal
    from utility import reference as R
    from utility import micro_ref
    from utility.calc import electricity_bill, gas_bill, water_bill
    from utility.check import assess, INTERNET_RANGE
    from utility.tariffs import ELECTRIC, GAS, WATER
from parse_ad_text import parse_ad

PORT = 8766
AREA_BANDS = {'~33㎡': '33㎡미만', '33~66㎡': '33-66㎡미만', '66~99㎡': '66-99㎡미만'}
HOUSING = {'단독·다가구': '단독', '다세대·연립': '다세대/연립/기타', '아파트': '아파트', '오피스텔': None}


def views_for(housing, household, area_band, gas_ok):
    v = []
    if HOUSING.get(housing):
        v.append(('housing', HOUSING[housing]))
    if household:                                     # 모르면(None) 그 관점을 건너뛴다. 임의로 1인 가구·소형으로 가정하지 않는다
        v.append(('size', f'{household}명' if household < 4 else '4명이상'))
    if area_band in AREA_BANDS:
        v.append(('area', AREA_BANDS[area_band]))
    return v, gas_ok


VIEW_LABEL = {'housing': '주택종류 평균', 'size': '가구원 수 평균', 'area': '면적 평균', 'heating': '도시가스 난방 가구 평균'}


def month_ref(month, housing, household, area_band, gas_ok):
    """한 달의 항목별 값. 전기·가스는 서로 다른 집단 평균(관점)을 각각 보존한다(조합·평균내지 않음). 민감도: 전기 +-20%, 가스 +-30% (가정)."""
    vs, _ = views_for(housing, household, area_band, gas_ok)
    out = {}
    for key, name, sens in (('electricity', 'electric', 0.2), ('gas', 'gas', 0.3)):
        if key == 'gas' and not gas_ok:
            out[name] = None
            continue
        views = list(vs) + ([('heating', '도시가스')] if key == 'gas' else [])
        if not views:                                   # 주택유형·가구원 수·면적을 모두 몰라 집단을 고를 수 없음
            out[name] = None
            continue
        by_view, vals, uses = [], [], []
        for view, cat in views:
            e = R.estimate(view, cat, month, household or 1)[key]
            by_view.append(dict(view=VIEW_LABEL[view], category=cat, bill=e['bill'], usage=e['usage']))
            vals.append(e['bill'])
            uses.append(e['usage'])
        mid = sum(uses) / len(uses)
        fn = (lambda u: electricity_bill(u, month)['total']) if key == 'electricity' else (lambda u: gas_bill(u)['total'])
        out[name] = dict(low=min(vals), high=max(vals), usage_low=min(uses), usage_high=max(uses), by_view=by_view,
                         sens=dict(pct=int(sens * 100), low=fn(mid * (1 - sens)), high=fn(mid * (1 + sens))))
    w = R.estimate('size', '1명', month, household)['water'] if household else None   # 수도는 가구원 수가 있어야 계산(관점과 무관)
    out['water'] = None if w is None else dict(low=w['bill'], high=w['bill'], usage_low=w['usage'], usage_high=w['usage'], by_view=[dict(view='서울 세대원 수별 평균 사용량', category=f'{household}명', bill=w['bill'], usage=w['usage'])])
    out['internet'] = dict(low=INTERNET_RANGE[0], high=INTERNET_RANGE[1], usage_low=None, usage_high=None,
                           by_view=[dict(view='KT 공개 요금제 예시(약정·결합에 따라 다름)', category='월 요금', bill=INTERNET_RANGE[0], usage=None), dict(view='KT 공개 요금제 예시', category='상위 속도', bill=INTERNET_RANGE[1], usage=None)])
    return out


QUESTIONS = {
    'electric': '전기는 사용량만큼 실비로 정산되나요, 정액인가요? 정액이면 월 몇 kWh 기준이고 초과분은 어떻게 하나요? 세대별 계량기가 있나요?',
    'water': '수도는 세대별 검침인가요, 건물 공동 계량을 나누는 방식인가요? 나누는 기준(인원·균등)이 무엇인가요?',
    'gas': '난방·온수가 개별 도시가스인가요, 중앙난방·지역난방인가요? 가스는 사용량대로 별도 청구인가요, 정액에 포함인가요?',
    'internet': '인터넷은 어떤 통신사·속도 상품인가요? 건물 단체계약이고 별도 가입이 필요 없나요?',
    '청소': '청소비는 어떤 공간을 몇 회 청소하는 비용인가요?',
    '공용전기': '공용전기(복도·엘리베이터·주차장) 요금을 세대에 어떻게 나누나요?',
    '승강기': '승강기 유지비가 포함되어 있나요? 저층에 사는 경우에도 부담하나요?',
}
NAMES = {'electric': '전기', 'water': '수도', 'gas': '가스', 'internet': '인터넷'}
ITEM_MAP = {'수도': 'water', '전기': 'electric', '가스': 'gas', '인터넷': 'internet'}


COMMON_ITEMS = ['일반관리비', '청소비', '경비비', '승강기 유지비', '공용 전기·수도', '난방비·급탕비(중앙난방일 때)', '건물 유지·수선']


def decompose(M, items, included, itemized, metering):
    """광고 관리비 M(원)을 광고상 확인 금액 / 참고 비용 대입 / 나머지로 나눈다. 실제 구성비가 아니다.
    - 포함 항목을 모르거나 총액이 없으면 분해하지 않는다. 포함 항목 중 계산 보류(HOLD)가 있거나 계량 방식이 세대별 실비가 아니면 구성비 산출을 보류한다.
    - 항목별 금액이 있는 항목은 그 금액만 쓰고 추정값을 더하거나 빼지 않는다. 참고 비용이 총액 이상이면 음수·0으로 만들지 않고 산출 어려움으로 둔다.
    - 미확인 항목을 0원으로 취급하지 않는다."""
    d = dict(type='NONE', M=M)
    if M is None:
        d['reason'] = '광고 관리비 총액이 없어 구성을 나누지 않습니다.'
        return d
    if not included:
        d['reason'] = '관리비에 포함되는 항목을 알 수 없어 구성을 나누지 않습니다(관리비 총액만 확인).'
        return d
    actual = {k: itemized[k] for k in included if k in itemized}
    rest = [k for k in included if k not in itemized]
    if any(items.get(k, {}).get('state') == 'HOLD' for k in rest):
        d['type'] = 'HOLD'
        d['reason'] = '포함 항목 중 참고 비용을 계산할 수 없는 항목(가스 사용·난방 방식 미확인 등)이 있어 구성비 산출을 보류합니다.'
        return d
    if rest and metering != '세대별':
        d['type'] = 'HOLD'
        d['reason'] = ('전기·수도·가스가 세대별 계량·실비 청구인지 알 수 없어(공동 계량·배분·정액 가능) 구성비 산출을 보류합니다. 참고 비용은 위 표에서 볼 수 있습니다.'
                       if metering in ('모름', None) else '공동 계량·배분 또는 정액 청구이면 서울 평균 사용료로 구성비를 계산할 수 없어 보류합니다.')
        d['can_assume'] = metering in ('모름', None)
        return d
    actual_sum = int(sum(actual.values()))
    u_low = sum(items[k]['low'] for k in rest)
    u_high = sum(items[k]['high'] for k in rest)
    d.update(actual_sum=actual_sum, actual_items=list(actual), ref_items=rest, U_low=u_low, U_high=u_high)
    if not rest:
        d['type'] = 'ACTUAL'
        d['label'] = '광고상 금액 미분류 부분'
        d['R_low'] = d['R_high'] = M - actual_sum
        if M - actual_sum < 0:
            d['type'], d['reason'] = 'HOLD', '항목별 광고 금액의 합이 관리비 총액보다 커서 구성을 나눌 수 없습니다. 입력을 확인해 주세요.'
        return d
    d['type'] = 'MIXED' if actual else 'VIRTUAL'
    d['label'] = '참고 가정에 따른 나머지 금액'
    if actual_sum + u_high >= M:
        d['type'], d['reason'] = 'HOLD', '현재 가정으로는 구성비 산출이 어렵습니다(참고 비용이 광고 관리비 이상이 될 수 있음). 정액제 할인·사용량 상한 등 다른 청구 구조일 수 있습니다.'
        return d
    d['R_low'] = M - actual_sum - u_high
    d['R_high'] = M - actual_sum - u_low
    d['pct_low'] = round(100 * d['R_low'] / M)
    d['pct_high'] = round(100 * d['R_high'] / M)
    return d


def bill_compare(month, usage):
    """고지서 사용량이 있으면 공식 요금표로 계산한 값을 돌려준다(전기 kWh, 수도 m3, 가스 N m3)."""
    out = {}
    for k, v in (usage or {}).items():
        if v in (None, ''):
            continue
        v = float(v)
        out[k] = electricity_bill(v, month)['total'] if k == 'electric' else (water_bill(v)['total'] if k == 'water' else gas_bill(v)['total'])
    return out


def estimate(p):
    month = max(1, min(int(p.get('month', 1)), 12))
    hh = p.get('household', 1)
    household = None if hh in (None, '') else max(1, min(int(hh), 6))
    housing, area_band = p.get('housing', '다세대·연립'), p.get('area_band', '~33㎡')
    heating, gas_user = p.get('heating', '모름'), p.get('gas_user', '모름')
    metering = p.get('metering', '모름')
    gas_ok = (gas_user == '예' and heating == '개별 도시가스')
    mgmt = p.get('mgmt_man')
    mgmt_won = int(round(float(mgmt) * 10000)) if mgmt not in (None, '') else None
    included = [ITEM_MAP[x] for x in p.get('included', []) if x in ITEM_MAP]
    other_included = [x for x in p.get('included', []) if x not in ITEM_MAP]
    itemized = {ITEM_MAP[k]: int(v) for k, v in (p.get('itemized') or {}).items() if k in ITEM_MAP and v not in (None, '')}
    series = {m: month_ref(m, housing, household, area_band, gas_ok) for m in range(1, 13)}
    cur = series[month]
    sep_keys = [ITEM_MAP[x] for x in p.get('excluded', []) if x in ITEM_MAP]
    shown = included or [k for k in NAMES if k not in sep_keys]    # 광고에 '별도 실비'로 적힌 항목은 관리비 안의 참고 합계에 넣지 않는다(이중 계산 방지)
    items = {}
    for it in shown:
        if it == 'gas' and cur['gas'] is None:
            items[it] = dict(name='가스', state='HOLD', reason='가스 사용 여부·난방 방식(개별 도시가스)이 확인되지 않아 참고 비용을 내지 않습니다.')
            continue
        if cur.get(it) is None:
            items[it] = dict(name=NAMES[it], state='HOLD', reason='가구원 수·주택유형·면적 중 필요한 조건이 없어 참고 비용을 내지 않습니다.')
            continue
        c = cur[it]
        items[it] = dict(name=NAMES[it], low=c['low'], high=c['high'], usage_low=c['usage_low'], usage_high=c['usage_high'], by_view=c['by_view'], sens=c.get('sens'))
    sum_low = sum(v['low'] for v in items.values() if 'low' in v)
    sum_high = sum(v['high'] for v in items.values() if 'high' in v)
    a = assess(month=month, household=household, included=included, itemized=itemized, mgmt_total=mgmt_won, gas_user=(gas_user == '예') or None,
               housing_cat=HOUSING.get(housing), area_cat=AREA_BANDS.get(area_band),
               heating='개별가스' if heating == '개별 도시가스' else (heating if heating != '모름' else None))
    questions = [QUESTIONS[x] for x in included if x in QUESTIONS] + [QUESTIONS[x] for x in other_included if x in QUESTIONS]
    if mgmt_won and mgmt_won >= 100000:
        questions.append('관리비가 월 10만원 이상이면 항목별 세부 내역(금액·산정 방식)을 서면으로 받을 수 있나요? (내역을 받지 못하는 사정이 있을 수 있어, 없다는 것만으로 문제라는 뜻은 아닙니다)')
    if not included and mgmt_won:
        questions.insert(0, '관리비 안에 포함되는 항목(전기·수도·가스·인터넷·청소 등)이 무엇인가요?')
    excluded_in = [ITEM_MAP[x] for x in p.get('excluded', []) if x in ITEM_MAP and ITEM_MAP[x] not in included]
    separate = {}
    for it in excluded_in:
        c = cur.get(it)
        separate[it] = dict(name=NAMES[it], hold=(c is None), low=(c or {}).get('low'), high=(c or {}).get('high'))
    monthly = {m: {NAMES[it]: dict(low=series[m][it]['low'], high=series[m][it]['high']) for it in shown if series[m].get(it)} for m in range(1, 13)}
    unver = []
    if not ELECTRIC['verified']['climate']:
        unver.append('기후환경요금 9원/kWh(공식 2026-10 적용 확인 전)')
    if not ELECTRIC['verified']['fund']:
        unver.append('전력산업기반기금율 2.7%(한전 원문 확인 전)')
    if not GAS['verified']['heat']:
        unver.append('도시가스 열량 43MJ/N㎥ 근사(고지서 값으로 대체 필요)')
    both = [NAMES[k] for k in included if k in sep_keys]
    if both:
        dec = dict(type='HOLD', M=mgmt_won, reason='같은 항목(' + '·'.join(both) + ')이 "포함"과 "별도" 양쪽에 선택되어 있어 구성을 나누지 않습니다. 입력을 확인해 주세요.')
    elif mgmt_won is not None and (mgmt_won < 0 or mgmt_won > 5000000):
        dec = dict(type='NONE', M=mgmt_won, reason='입력한 관리비가 범위를 벗어났습니다(음수이거나 월 500만원 초과). 단위(만원)를 확인해 주세요.')
    else:
        dec = decompose(mgmt_won, items, included, itemized, metering)
    micro = None
    if micro_ref.available():                               # 분포표(로컬 전용 파생 통계)가 있을 때만
        el = micro_ref.pick('electric_kwh', month, household, p.get('area_band', '~33㎡'))
        if el is not None:                                  # 전기만: 사전 등록 평가를 통과한 부분 풀링 분위수를 함께 준다(가구원 수가 있을 때)
            el['pooled'] = micro_ref.pooled('electric_kwh', month, household, p.get('area_band', '~33㎡')) if household else None
        micro = dict(electric=el,
                     gas=micro_ref.pick('gas_nm3', month, household, p.get('area_band', '~33㎡')) if gas_ok else None)
    return dict(month=month, items=items, sum_low=sum_low, sum_high=sum_high, mgmt_won=mgmt_won, status=a['status'], assess_items=a['items'],
                questions=questions, monthly=monthly, unverified=unver, other_included=other_included, separate=separate, decomposition=dec,
                bill_check=bill_compare(month, p.get('bill_usage')), common_items=COMMON_ITEMS,
                micro=micro,
                meta=dict(tariff_date='2026-10-20 확인(한전 주택용 저압, 서울가스 2026.10.01, 아리수 가정용)', usage_basis='가구에너지패널조사 14차(2023년 기준) 서울 결과표',
                          note='2023년 사용량을 2026년 요율로 환산한 참고 금액이며 실제 2026년 평균 청구액이 아님', kinds='서로 다른 집단 평균을 각각 환산한 값(조합하지 않음)',
                          month_used=f'{month}월 기준 한 달치(월·난방 방식이 다르면 비교하지 마세요)'),
                basis='서울 가구 평균 사용량(가구에너지패널 2023) × 2026년 요율. 표시하는 폭은 서로 다른 집단(주택종류·가구원 수·면적) 평균을 각각 환산한 값들의 최소~최대이며, 개인 가구의 정상 범위가 아닙니다.')


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
        else:
            self._send(404, 'not found', 'text/plain')

    def do_POST(self):
        try:
            n = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(n).decode('utf-8'))
            if self.path == '/estimate':
                res = estimate(body)
            elif self.path == '/parse':
                res = parse_ad(str(body.get('text', '')))
            else:
                return self._send(404, 'not found', 'text/plain')
        except Exception as e:
            res = dict(error='입력을 처리하지 못했습니다. 값을 확인해 주세요.')
            print('오류:', type(e).__name__, e, flush=True)
        self._send(200, json.dumps(res, ensure_ascii=False, default=lambda o: None), 'application/json; charset=utf-8')

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), H)
    url = f'http://127.0.0.1:{PORT}/'
    print('관리비 점검 데모:', url, '(종료: Ctrl+C)', flush=True)
    if '--no-browser' not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
