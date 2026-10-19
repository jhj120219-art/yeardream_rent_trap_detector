import csv
import io
import zipfile
import pytest
from backend.scripts.prepare_seoul_file import COLUMNS, prepare


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
