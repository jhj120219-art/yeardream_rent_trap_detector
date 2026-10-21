import pytest
from backend.app.advertised_costs import advertised_costs
from backend.app.db import Store
from backend.tests.test_backend import setup,payload
from backend.tests.test_mysql_persistence import target
from backend.tests.test_advertised_costs import quoted_input
from backend.scripts.backfill_maintenance import backfill

CODES=['ELECTRICITY','WATER','GAS','INTERNET','OTHER']


def test_new_input_has_five_rows_zero_unknown_and_no_inferred_remainder(setup):
    c,_=setup
    body=payload();body['options'].update(maintenance_10k_krw=7,other_in_maintenance='INCLUDED',other_10k_krw=0)
    lid=c.post('/listings',json=body).json()['id']
    result=c.get('/listings/'+lid+'/report').json()['advertised_costs']
    assert result['category_version']=='FIVE_ITEMS_V1'
    assert [x['item'] for x in result['items']]==CODES
    assert result['items'][-1]['quoted_monthly_10k_krw']==0
    assert result['items'][0]['quoted_monthly_10k_krw'] is None
    assert 'legacy_components' not in result['items'][-1]
    assert c.get('/capabilities').json()['advertised_cost_categories']==CODES
    unknown=advertised_costs({'maintenance_10k_krw':7},True)
    assert all(x['quoted_monthly_10k_krw'] is None for x in unknown['items'])
    with c.app.state.store.connect() as db:
        assert db.execute('SELECT COUNT(*) AS n FROM listing_maintenance_items WHERE listing_id=?',(lid,)).fetchone()['n']==5


def test_existing_seven_rows_are_preserved_and_read_as_five(target):
    path,url=target;store=Store(path,database_url=url)
    owner=store.owner(store.session());body=quoted_input()
    try:
        lid=store.create(owner,'listing',{'input':body})['id']
        with store.connect() as db:
            db.execute('DELETE FROM listing_maintenance_items WHERE listing_id=?',(lid,))
            legacy=[('ELECTRICITY','SEPARATE_CHARGE',None,None),('WATER','INCLUDED',1,None),
                    ('GAS','UNKNOWN',None,None),('INTERNET','UNKNOWN',None,None),
                    ('CLEANING','INCLUDED',0,None),('COMMON','UNKNOWN',None,None),('OTHER','SEPARATE_CHARGE',3,body['options']['other_cost_label'])]
            for item,status,amount,label in legacy:
                raw_status='AVAILABLE' if item=='INTERNET' else status
                db.execute('INSERT INTO listing_maintenance_items VALUES(?,?,?,?,?,?)',(lid,item,status,raw_status,amount,label))
        quote=store.maintenance(lid,owner)
        assert [x['item'] for x in quote['items']]==CODES
        other=quote['items'][-1]
        assert other['needs_review'] and other['status']=='UNKNOWN' and other['quoted_monthly_10k_krw'] is None
        details={x['item']:x for x in other['legacy_components']}
        assert details['CLEANING']['quoted_monthly_10k_krw']==0
        assert details['OTHER']['quoted_monthly_10k_krw']==3
        assert store.get(lid,owner,'listing')['input']==body
        assert backfill(store)['inserted_listings']==0
        with store.connect() as db:
            assert db.execute('SELECT COUNT(*) AS n FROM listing_maintenance_items WHERE listing_id=?',(lid,)).fetchone()['n']==7
            db.execute("DELETE FROM listing_maintenance_items WHERE listing_id=? AND item='COMMON'",(lid,))
        with pytest.raises(ValueError,match='Incomplete'):store.maintenance(lid,owner)
    finally:store.delete_session(owner)
