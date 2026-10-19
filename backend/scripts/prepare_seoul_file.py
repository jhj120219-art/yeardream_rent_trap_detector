"""서울시 공개 FILE ZIP의 한글 열을 기존 수집기 열로 연결한다. 분석 정책은 변경하지 않는다."""
import argparse
import csv
import io
import json
from pathlib import Path
import zipfile

COLUMNS = {
    '자치구코드': 'CGG_CD', '자치구명': 'CGG_NM',
    '법정동코드': 'STDG_CD', '법정동명': 'STDG_NM',
    '본번': 'MNO', '부번': 'SNO', '층': 'FLR', '계약일': 'CTRT_DAY',
    '전월세구분': 'RENT_SE', '임대면적': 'RENT_AREA',
    '보증금(만원)': 'GRFE', '임대료(만원)': 'RTFE',
    '건물명': 'BLDG_NM', '건축년도': 'ARCH_YR',
    '건물용도': 'BLDG_USG', '신규계약구분': 'NEW_UPDT_YN',
}
SUPPORTED = {'11620', '11215', '11440', '11590', '11500', '11350'}


def prepare(source: Path, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    total = selected = 0
    with zipfile.ZipFile(source) as archive:
        members = [x for x in archive.infolist() if x.filename.lower().endswith('.csv')]
        if len(members) != 1:
            raise ValueError('Expected exactly one CSV member')
        with archive.open(members[0]) as stream:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding='cp949'))
            if not set(COLUMNS).issubset(reader.fieldnames or []):
                raise ValueError('Official file columns differ; review mapping before importing')
            # 기존 파일은 교체하지 않으며 실패 시 이번에 만든 파일만 제거한다.
            with target.open('x', encoding='utf-8-sig', newline='') as out:
                try:
                    writer = csv.DictWriter(out, fieldnames=list(COLUMNS.values()))
                    writer.writeheader()
                    for row in reader:
                        total += 1
                        if row['자치구코드'] not in SUPPORTED:
                            continue
                        writer.writerow({dest: row[name] for name, dest in COLUMNS.items()})
                        selected += 1
                except Exception:
                    out.close()
                    target.unlink()
                    raise
    return {'source_rows': total, 'selected_rows': selected, 'district_count': len(SUPPORTED)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.zip, args.out)))
