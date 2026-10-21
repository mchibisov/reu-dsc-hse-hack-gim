"""One-off test-only auth check; refuses any server outside our disposable cluster."""
import json
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql

root = Path(__file__).resolve().parents[3]
cluster = (root / 'runtime/pgtest').resolve()
with psycopg.connect('postgresql://gim_test@127.0.0.1:55439/gim_private_test', autocommit=True) as c:
    actual = Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()
    if actual != cluster or c.info.port != 55439 or c.info.dbname != 'gim_private_test':
        raise RuntimeError('Not our disposable test cluster')
    secret = uuid4().hex
    c.execute(sql.SQL('ALTER ROLE gim_test PASSWORD {}').format(sql.Literal(secret)))
    (root / 'runtime/test_auth.json').write_text(json.dumps({'password': secret}), encoding='utf-8')
    hba = cluster / 'pg_hba.conf'
    previous = hba.read_text(encoding='utf-8')
    hba.write_text('host all all 127.0.0.1/32 scram-sha-256\n' + previous, encoding='utf-8')
    assert c.execute('SELECT pg_reload_conf()').fetchone()[0]
print('SCRAM enabled only for the disposable localhost test cluster; no credentials printed')
