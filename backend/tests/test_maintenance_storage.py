import json
import pytest
from backend.app.db import Store
from backend.app.advertised_costs import advertised_costs
from backend.app.maintenance_storage import project
from backend.scripts.backfill_maintenance import backfill
from backend.tests.test_advertised_costs import quoted_input
from backend.tests.test_mysql_persistence import target


def test_relational_rows_match_output_and_original_survives(target):
    path,url=target
    store=Store(path,database_url=url)
    token=store.session();owner=store.owner(token)
    raw=quoted_input(); payload={'input':raw}
    listing=None
    try:
        listing=store.create(owner,'listing',payload)
        lid=listing['id']
        assert store.maintenance(lid,owner)==advertised_costs(raw['options'],True)
        assert store.get(lid,owner,'listing')['input']==raw
        with store.connect() as db:
            fee=db.execute('SELECT * FROM listing_maintenance WHERE listing_id=?',(lid,)).fetchone()
            items={r['item']:r for r in db.execute('SELECT * FROM listing_maintenance_items WHERE listing_id=?',(lid,)).fetchall()}
            assert fee['amount_10k_krw']==7
            assert len(items)==7
            assert items['WATER']['status']=='INCLUDED' and items['WATER']['amount_10k_krw']==1
            assert items['ELECTRICITY']['amount_10k_krw'] is None
            assert items['CLEANING']['amount_10k_krw']==0
            assert items['INTERNET']['raw_status']=='AVAILABLE' and items['INTERNET']['status']=='UNKNOWN'
            assert items['OTHER']['label']=='주차'
        assert store.maintenance(lid,'another-owner') is None
        reopened=Store(path,database_url=url,initialize=False)
        assert reopened.maintenance(lid,owner)==store.maintenance(lid,owner)
        assert store.delete(lid,owner,'listing')
        with store.connect() as db:
            assert db.execute('SELECT COUNT(*) AS total FROM listing_maintenance_items WHERE listing_id=?',(lid,)).fetchone()['total']==0
    finally:
        store.delete_session(owner)


def test_backfill_idempotent_and_conflict_rolls_back(target):
    path,url=target;store=Store(path,database_url=url)
    owner=store.owner(store.session())
    try:
        raw=quoted_input();lid=store.create(owner,'listing',{'input':raw})['id']
        with store.connect() as db:
            db.execute('DELETE FROM listing_maintenance WHERE listing_id=?',(lid,))
        assert backfill(store)['inserted_listings']==1
        assert backfill(store)['inserted_listings']==0
        assert store.maintenance(lid,owner)==advertised_costs(raw['options'],True)
        with store.connect() as db:
            db.execute('UPDATE listing_maintenance SET amount_10k_krw=? WHERE listing_id=?',(99,lid))
        with pytest.raises(ValueError,match='differs'):
            backfill(store)
        assert store.get(lid,owner,'listing')['input']['options']['maintenance_10k_krw']==7
    finally:store.delete_session(owner)


def test_listing_and_items_rollback_together(target,monkeypatch):
    path,url=target;store=Store(path,database_url=url)
    owner=store.owner(store.session())
    from backend.app import maintenance_storage
    def fail(db,lid,payload):
        project(db,lid,payload)
        raise RuntimeError('interrupted')
    monkeypatch.setattr(maintenance_storage,'project',fail)
    try:
        with pytest.raises(RuntimeError):store.create(owner,'listing',{'input':quoted_input()})
        assert store.page(owner,'listing',20,0)['items']==[]
        with store.connect() as db:
            assert db.execute('SELECT COUNT(*) AS total FROM listing_maintenance').fetchone()['total']==0
    finally:store.delete_session(owner)
from pathlib import Path
from types import SimpleNamespace
from backend.app.db import Store
from backend.scripts.import_maintenance_examples import import_examples
import pytest


def test_example_json_split_is_atomic_and_separate(tmp_path):
    store=Store(tmp_path/'examples.sqlite3')
    wrapped=SimpleNamespace(mysql=True,options={'database':'rent_examples_unit'},connect=store.connect)
    files=[Path('backend/examples/api_responses.json'),Path('backend/examples/utility_estimates.json')]
    counts=import_examples(wrapped,files)
    assert counts['sources']==2 and counts['maintenance_rows']>0
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) AS total FROM listing_maintenance').fetchone()['total']==counts['maintenance_rows']
        assert db.execute('SELECT COUNT(*) AS total FROM listing_maintenance_items').fetchone()['total']==counts['maintenance_rows']*7
        assert db.execute("SELECT COUNT(*) AS total FROM objects WHERE kind='synthetic_import_source'").fetchone()['total']==2
    with pytest.raises(ValueError,match='empty'):import_examples(wrapped,files)
    wrapped.options['database']='rent_team'
    with pytest.raises(ValueError,match='separate'):import_examples(wrapped,files)
