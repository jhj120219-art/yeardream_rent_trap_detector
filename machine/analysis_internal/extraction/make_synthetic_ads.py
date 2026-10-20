# -*- coding: utf-8 -*-
"""합성 광고 이미지(회귀 테스트용) + 정답 JSON 생성. 실제 광고가 아니며 성능을 주장하는 용도가 아니다.
HTML -> headless Chrome 스크린샷. 결과: extraction/synthetic/ad_XX.png, ground_truth.json"""
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'synthetic'
OUT.mkdir(exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# (제목줄, 가격 문구, 부가 설명 줄들, 정답)
CASES = [
    ('신림역 도보 5분 깨끗한 원룸', '보증금 1,000만원 / 월세 50만원', ['관리비 7만원 (수도, 인터넷 포함)', '전용면적 20㎡ · 3층 / 5층', '서울 관악구 신림동 · 빌라(다세대)', '남향, 풀옵션'],
     dict(deposit=1000, rent=50, maint=7, included=['수도', '인터넷'], excluded=[], area=20, area_basis='전용', floor='3', dong='신림동', gu='관악구')),
    ('봉천동 투룸 급매', '보증금 500 / 월세 45', ['관리비: 별도 (사용량만큼 실비)', '전용 33.5㎡ · 2층', '서울 관악구 봉천동 · 다가구주택'],
     dict(deposit=500, rent=45, maint=None, included=[], excluded=[], area=33.5, area_basis='전용', floor='2', dong='봉천동', gu='관악구')),
    ('합정동 신축 오피스텔', '보증금 2,000만원 / 월세 70만원', ['관리비 10만원 (인터넷·수도·청소비 포함, 전기·가스 별도)', '전용 24㎡ · 8층', '서울 마포구 합정동 · 오피스텔'],
     dict(deposit=2000, rent=70, maint=10, included=['인터넷', '수도', '청소'], excluded=['전기', '가스'], area=24, area_basis='전용', floor='8', dong='합정동', gu='마포구')),
    ('상도동 저렴한 원룸', '월세 40만원 / 보증금 300만원', ['관리비 없음 (공과금 별도)', '전용 16㎡ · 4층', '서울 동작구 상도동 · 다세대주택'],
     dict(deposit=300, rent=40, maint=0, included=[], excluded=['공과금'], area=16, area_basis='전용', floor='4', dong='상도동', gu='동작구')),
    ('노원 반지하 투룸', '보증금 1억 / 월세 45만원', ['관리비 12만원 (전기·수도·인터넷 포함)', '전용 29㎡ · 반지하', '서울 노원구 공릉동 · 연립주택'],
     dict(deposit=10000, rent=45, maint=12, included=['전기', '수도', '인터넷'], excluded=[], area=29, area_basis='전용', floor='반지하', dong='공릉동', gu='노원구')),
    ('광진구 자양동 원룸', '보증금 1,000 / 월세 55', ['관리비 5.5만원 (수도 포함)', '전용 18㎡ (공급 26㎡) · 6층', '서울 광진구 자양동 · 오피스텔'],
     dict(deposit=1000, rent=55, maint=5.5, included=['수도'], excluded=[], area=18, area_basis='전용', floor='6', dong='자양동', gu='광진구')),
    ('강서구 화곡동 신축 빌라', '월세 500/45', ['관리비 8만원 포함: 인터넷 · 가스(난방) · 공용전기', '전용 22㎡ · 1층', '서울 강서구 화곡동 · 신축 빌라'],
     dict(deposit=500, rent=45, maint=8, included=['인터넷', '가스', '공용전기'], excluded=[], area=22, area_basis='전용', floor='1', dong='화곡동', gu='강서구')),
    ('성수동 풀옵션 스튜디오', '보증금 2,000만원 / 월세 60만원', ['관리비 15만원', '전용 26㎡ · 5층', '서울 성동구 성수동1가 · 오피스텔', '※ 인터넷, 수도 포함 / 전기는 각 호실 별도 청구'],
     dict(deposit=2000, rent=60, maint=15, included=['인터넷', '수도'], excluded=['전기'], area=26, area_basis='전용', floor='5', dong='성수동1가', gu='성동구')),
]

HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
body{{margin:0;width:700px;font-family:'Malgun Gothic','Noto Sans KR',sans-serif;background:#fff;color:#222}}
.hd{{background:#2b7fff;color:#fff;padding:18px 24px;font-size:22px;font-weight:700}}
.img{{height:150px;background:linear-gradient(135deg,#cfd8e3,#e8edf3)}}
.t{{padding:18px 24px 6px;font-size:26px;font-weight:700}}
.p{{padding:6px 24px;font-size:30px;font-weight:800;color:#d8242b}}
.l{{padding:5px 24px;font-size:20px;color:#444}}
.ft{{padding:18px 24px;font-size:15px;color:#888}}
</style></head><body><div class="hd">부동산 매물</div><div class="img"></div>
<div class="t">{title}</div><div class="p">{price}</div>{lines}<div class="ft">연락처 010-****-**** (가림) · 등록일 2026.10.18</div></body></html>"""


def main():
    gt = {}
    for i, (title, price, lines, truth) in enumerate(CASES, 1):
        name = f'ad_{i:02d}'
        html = HTML.format(title=title, price=price, lines=''.join(f'<div class="l">{x}</div>' for x in lines))
        hp = OUT / f'{name}.html'
        hp.write_text(html, encoding='utf-8')
        png = OUT / f'{name}.png'
        subprocess.run([CHROME, '--headless=new', '--disable-gpu', f'--screenshot={png}', '--window-size=700,520', '--hide-scrollbars',
                        f'--user-data-dir={OUT / "chrome_profile"}', hp.as_uri()], capture_output=True, timeout=60)
        gt[name] = truth
        print(name, png.exists())
    (OUT / 'ground_truth.json').write_text(json.dumps(gt, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
