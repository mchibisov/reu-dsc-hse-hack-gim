import os
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict,make_conninfo
import pytest
from gim.local_setup import initialize

DSN=os.environ.get('TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not DSN,reason='disposable PostgreSQL required')

@pytest.fixture
def local_database():
    name='gim_quick_'+uuid4().hex
    params=conninfo_to_dict(DSN)
    with psycopg.connect(DSN,autocommit=True) as c:
        c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    dsn=make_conninfo(**{**params,'dbname':name})
    yield dsn
    # Test-created database only; runtime logins own no database objects.
    with psycopg.connect(dsn) as c:
        owned=c.execute("SELECT to_regclass('gim_local.installation')").fetchone()[0]
        token=c.execute("SELECT config->>'installation_id' FROM gim_local.installation").fetchone()[0] if owned else None
        roles=[('gim_local_'+role+'_'+token[:12],) for role in ('bot','worker','staff')] if token else []
    with psycopg.connect(DSN,autocommit=True) as c:
        c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
        for role, in roles:
            # Never touch another installation's login.
            try:c.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
            except psycopg.errors.DependentObjectsStillExist:pass


def test_foreign_nonempty_database_is_never_migrated(local_database,tmp_path):
    with psycopg.connect(local_database) as c:
        c.execute('CREATE TABLE public.unrelated(value text)')
        c.execute("INSERT INTO public.unrelated VALUES('preserve me')")
    with pytest.raises(ValueError,match='existing database'):
        initialize(local_database,123,456,tmp_path/'runtime.json')
    with psycopg.connect(local_database) as c:
        assert c.execute('SELECT value FROM public.unrelated').fetchone()[0]=='preserve me'
        assert c.execute("SELECT to_regnamespace('gim')").fetchone()[0] is None


def test_fresh_bootstrap_restart_and_changed_owner_guard(local_database,tmp_path):
    path=tmp_path/'runtime.json'
    initialize(local_database,123,456,path)
    original=path.read_bytes()
    initialize(local_database,123,456,path)
    assert path.read_bytes()==original
    with pytest.raises(ValueError):initialize(local_database,123,999,path)
    with psycopg.connect(local_database) as c:
        assert c.execute("SELECT count(*) FROM gim.question_templates WHERE kind='base'").fetchone()[0]==18
        assert c.execute('SELECT count(*) FROM gim.recruitments').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM gim.staff_members WHERE active').fetchone()[0]==1
