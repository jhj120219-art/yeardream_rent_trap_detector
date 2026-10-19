import csv
import io
import zipfile
import pytest
from backend.scripts.prepare_seoul_file import COLUMNS, EXPORT_ALIASES, prepare


def test_official_file_mapping_preserves_units_and_codes(tmp_path):
    text = io.StringIO(newline='')
    writer = csv.DictWriter(text, fieldnames=list(COLUMNS))
    writer.writeheader()
    row = dict.fromkeys(COLUMNS, '')
    row.update({'자치구코드': '11620', '법정동코드': '10100', '임대료(만원)': '50',
                '보증금(만원)': '5000', '임대면적': '59.9', '신규계약구분': '신규'})
    writer.writerow(row)
    writer.writerow(dict(row, 자치구코드='11710'))
    source, target = tmp_path/'source.zip', tmp_path/'result.csv'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('data.csv', text.getvalue().encode('cp949'))
    result = prepare(source, target)
    assert (result['source_rows'], result['selected_rows']) == (2, 1)
    with target.open(encoding='utf-8-sig', newline='') as stream:
        saved = list(csv.DictReader(stream))
    assert saved[0]['CGG_CD'] == '11620'
    assert saved[0]['STDG_CD'] == '10100'
    assert saved[0]['RTFE'] == '50'
    assert saved[0]['GRFE'] == '5000'
    assert saved[0]['RENT_AREA'] == '59.9'
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        prepare(source, target)
    assert target.read_bytes() == before


def test_changed_official_header_is_not_guessed(tmp_path):
    source, target = tmp_path/'source.zip', tmp_path/'result.csv'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('data.csv', b'unknown\n1\n')
    with pytest.raises(ValueError):
        prepare(source, target)
    assert not target.exists()


def test_current_year_sheet_export_and_receipt_year_validation(tmp_path):
    source, target = tmp_path/'current.csv', tmp_path/'result.csv'
    header = ['접수연도']+[EXPORT_ALIASES.get(name, name) for name in COLUMNS]
    row = dict.fromkeys(header, '')
    row.update({'접수연도': '2026', '자치구코드': '11620', '임대면적(㎡)': '59.9',
                '전월세 구분': '월세', '신규갱신여부': '신규', '임대료(만원)': '50'})
    with source.open('w', encoding='cp949', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=header)
        writer.writeheader()
        writer.writerow(row)
    result = prepare(source, target, year=2026)
    assert result['verified_receipt_year'] == 2026
    with target.open(encoding='utf-8-sig', newline='') as stream:
        saved = next(csv.DictReader(stream))
    assert saved['RCPT_YR'] == '2026'
    assert saved['RENT_AREA'] == '59.9'
    assert saved['NEW_UPDT_YN'] == '신규'
    wrong = tmp_path/'wrong.csv'
    with pytest.raises(ValueError, match='Unexpected receipt year'):
        prepare(source, wrong, year=2025)
    assert not wrong.exists()


def test_requested_year_requires_a_receipt_year_column(tmp_path):
    source = tmp_path/'without_year.csv'
    with source.open('w', encoding='cp949', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=list(COLUMNS))
        writer.writeheader()
    with pytest.raises(ValueError, match='Receipt year column required'):
        prepare(source, tmp_path/'result.csv', year=2026)
