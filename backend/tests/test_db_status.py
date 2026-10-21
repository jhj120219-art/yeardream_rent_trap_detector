from backend.app.db import Store
from backend.tests.test_mysql_persistence import target
from backend.tests.test_backend import payload
from backend.scripts.db_status import inspect


def test_aggregate_counts_preserve_data_and_exclude_secrets(target):
    path,url=target;store=Store(path,database_url=url)
    baseline=inspect(store)
    owner=store.owner(store.session())
    try:
        raw=payload();listing=store.create(owner,'listing',{'input':raw})
        counts=inspect(store)
        assert counts['maintenance_total_rows']==baseline['maintenance_total_rows']+1
        assert counts['maintenance_item_rows']==baseline['maintenance_item_rows']+5
        assert counts['listings_by_item_count']['5']==baseline['listings_by_item_count'].get('5',0)+1
        assert counts['objects_by_kind']['listing']==baseline['objects_by_kind'].get('listing',0)+1
        assert counts['raw_user_data_included'] is False
        assert counts['changes_performed'] is False
        assert store.get(listing['id'],owner,'listing')['input']==raw
        assert listing['id'] not in str(counts) and owner not in str(counts)
        assert inspect(store)==counts
    finally:store.delete_session(owner)
