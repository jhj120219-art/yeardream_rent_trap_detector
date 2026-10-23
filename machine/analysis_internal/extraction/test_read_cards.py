# -*- coding: utf-8 -*-
"""read_cards.py 시험(OCR 패키지 없이, 가짜 박스로). 열 분리가 같은 건물 매물 두 칸을 섞지 않는지, 합의 동작을 확인한다. 사용: python test_read_cards.py"""
from ad_cards import cards_from
from consensus import consensus
from read_cards import KEY, cards_from_boxes, lines_by_column, lines_from_boxes, norm


def box(x, y, text, w=150, h=24):
    return ([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], text, 0.9)


# 가로 두 칸: 왼쪽 카드(전세 1억3000, 2층 23.14m² 관리비 5만), 오른쪽 카드(월세 500/55, 2층 18.18m² 관리비 5만)
TWO_UP = [box(15, 100, '전세 1억3000'), box(215, 100, '월세 500/55'), box(15, 160, '원룸'), box(215, 160, '원룸'),
          box(15, 190, '2층, 23.14m², 관리비 5만', 170), box(215, 190, '2층, 18.18m², 관리비 5만', 170)]
ONE_COL = [box(15, 100, '월세 1000/52'), box(15, 160, '원룸'), box(15, 190, '3층, 27m², 관리비 9만', 170),
           box(15, 400, '월세 500/40'), box(15, 460, '원룸'), box(15, 490, '2층, 20m², 관리비 8만', 170)]


def main():
    bad = []
    # 1) 기존 줄 묶기는 두 칸을 섞고(오독 재현), 열 분리는 섞지 않는다
    mixed = {KEY(c) for c in cards_from(norm('\n'.join(lines_from_boxes(TWO_UP))))}
    split = cards_from_boxes(TWO_UP, 400)
    if ('월세', 500.0, 55.0, 18.18, 5.0) not in split or ('월세', 500.0, 55.0, 23.14, 5.0) in split:
        bad.append(('열 분리 결과', split))
    if ('월세', 500.0, 55.0, 23.14, 5.0) not in mixed:
        bad.append(('기존 줄 묶기가 섞이는 상황이 재현되지 않음(시험 전제 변경)', mixed))
    # 2) 한 열 화면은 그대로 두 카드를 읽는다
    one = cards_from_boxes(ONE_COL, 400)
    if one != {('월세', 1000.0, 52.0, 27.0, 9.0), ('월세', 500.0, 40.0, 20.0, 8.0)}:
        bad.append(('한 열 화면', one))
    # 3) 엔진 합의: 두 엔진이 같게 읽은 값만 extracted
    res = consensus({'a': sorted(one), 'b': [('월세', 1000.0, 52.0, 27.0, 9.0)]})
    if sum(c['status'] == 'extracted' for c in res) != 1 or not any(c['status'] == 'on_hold' for c in res):
        bad.append(('합의', res))
    # 4) 줄 순서: 왼쪽 열 전체 다음 오른쪽 열
    ls = lines_by_column(TWO_UP, 400)
    if ls.index('전세 1억3000') > ls.index('월세 500/55') or ls.index('월세 500/55') < ls.index('2층, 23.14m², 관리비 5만'):
        bad.append(('줄 순서', ls))
    print('실패 %d 건' % len(bad), *bad, sep='\n' if bad else ' ')
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
