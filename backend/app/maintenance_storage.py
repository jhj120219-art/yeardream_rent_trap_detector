"""Relational projection of advertised maintenance facts; original listing JSON stays intact."""
import json
from .advertised_costs import ITEMS, LEGACY_ITEMS, STORAGE_ITEMS, STATUSES, advertised_costs

MYSQL_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS listing_maintenance (listing_id VARCHAR(36) PRIMARY KEY, amount_10k_krw DOUBLE, user_confirmed BOOLEAN NOT NULL, note TEXT, FOREIGN KEY(listing_id) REFERENCES objects(id) ON DELETE CASCADE)",
    "CREATE TABLE IF NOT EXISTS listing_maintenance_items (listing_id VARCHAR(36) NOT NULL, item VARCHAR(16) NOT NULL, status VARCHAR(24) NOT NULL, raw_status VARCHAR(32), amount_10k_krw DOUBLE, label TEXT, PRIMARY KEY(listing_id,item), FOREIGN KEY(listing_id) REFERENCES listing_maintenance(listing_id) ON DELETE CASCADE, CHECK(status IN ('INCLUDED','SEPARATE_CHARGE','UNKNOWN')), CHECK(item IN ('ELECTRICITY','WATER','GAS','INTERNET','CLEANING','COMMON','OTHER')))",
)
SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS listing_maintenance (
 listing_id TEXT PRIMARY KEY REFERENCES objects(id) ON DELETE CASCADE,
 amount_10k_krw REAL, user_confirmed INTEGER NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS listing_maintenance_items (
 listing_id TEXT NOT NULL REFERENCES listing_maintenance(listing_id) ON DELETE CASCADE,
 item TEXT NOT NULL CHECK(item IN ('ELECTRICITY','WATER','GAS','INTERNET','CLEANING','COMMON','OTHER')),
 status TEXT NOT NULL CHECK(status IN ('INCLUDED','SEPARATE_CHARGE','UNKNOWN')),
 raw_status TEXT, amount_10k_krw REAL, label TEXT, PRIMARY KEY(listing_id,item));
"""


def project(db, listing_id, payload):
    raw = payload.get('input', {})
    options = raw.get('options', {})
    confirmed = raw.get('confirmation', {}).get('user_confirmed', False)
    quote = advertised_costs(options, confirmed)
    db.execute('INSERT INTO listing_maintenance VALUES(?,?,?,?)',
               (listing_id, quote['maintenance_10k_krw'], bool(confirmed), quote['note']))
    for item in quote['items']:
        status_field, _ = ITEMS[item['item']]
        db.execute('INSERT INTO listing_maintenance_items VALUES(?,?,?,?,?,?)',
                   (listing_id, item['item'], item['status'], options.get(status_field),
                    item['quoted_monthly_10k_krw'], item['label']))


def read(db, listing_id, owner):
    row = db.execute("SELECT m.*,o.payload AS original_payload FROM listing_maintenance m JOIN objects o ON o.id=m.listing_id "
                     "WHERE o.id=? AND o.owner=? AND o.kind='listing'", (listing_id, owner)).fetchone()
    if row is None:
        return None
    options = {'maintenance_10k_krw': row['amount_10k_krw'], 'maintenance_note': row['note']}
    items = db.execute('SELECT * FROM listing_maintenance_items WHERE listing_id=?', (listing_id,)).fetchall()
    codes={item['item'] for item in items}
    if codes not in (set(ITEMS),set(STORAGE_ITEMS)):
        raise ValueError('Incomplete maintenance projection; run verified backfill before deployment')
    for item in items:
        status_field, amount_field = STORAGE_ITEMS[item['item']]
        options[status_field] = item['status']
        options[amount_field] = item['amount_10k_krw']
        if item['item'] == 'OTHER':
            options['other_cost_label'] = item['label']
    if codes == set(ITEMS):
        original=json.loads(row['original_payload']).get('input',{}).get('options',{})
        legacy={field:original[field] for pair in LEGACY_ITEMS.values() for field in pair if field in original}
        if legacy:
            legacy.update({field:original.get(field) for field in (*ITEMS['OTHER'],'other_cost_label')})
            candidate=advertised_costs({**options,**legacy},bool(row['user_confirmed']))
            stored=next(item for item in items if item['item']=='OTHER')
            other=candidate['items'][-1]
            if stored['status']!=other['status'] or stored['amount_10k_krw']!=other['quoted_monthly_10k_krw']:
                raise ValueError('Legacy projection differs from stored OTHER row')
            return candidate
    return advertised_costs(options, bool(row['user_confirmed']))
