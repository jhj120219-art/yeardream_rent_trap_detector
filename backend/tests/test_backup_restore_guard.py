from pathlib import Path
import pytest
from backend.scripts import verify_local_mysql_backup as verifier


@pytest.mark.parametrize('sql',[b'',b'USE rent_team;\n',b'CREATE DATABASE rent_team;\n',b'DROP DATABASE rent_team;\n'])
def test_restore_rejects_empty_or_database_switching_dump_before_connection(tmp_path,monkeypatch,sql):
    backups=tmp_path/'backups';backups.mkdir()
    dump=backups/'rent_team-test.sql';dump.write_bytes(sql)
    monkeypatch.setattr(verifier,'configuration',lambda runtime:(tmp_path,tmp_path,{}))
    def unexpected(*args):raise AssertionError('Must not open DB for unsafe dump')
    monkeypatch.setattr(verifier,'connect',unexpected)
    with pytest.raises(ValueError):verifier.verify(tmp_path,'rent_team',dump)


def test_restore_rejects_files_outside_private_backups(tmp_path,monkeypatch):
    dump=tmp_path/'rent_team-test.sql';dump.write_text('SELECT 1;')
    monkeypatch.setattr(verifier,'configuration',lambda runtime:(tmp_path,tmp_path,{}))
    with pytest.raises(ValueError):verifier.verify(tmp_path,'rent_team',dump)
