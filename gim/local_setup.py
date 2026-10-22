"""Isolated Docker bootstrap. Never accepts a production DSN from the environment."""
import json
import os
from pathlib import Path
import secrets
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo, conninfo_to_dict
from psycopg.types.json import Jsonb
from gim_db.migrate import migrate

ROOT=Path(__file__).resolve().parents[1]
CONFIG=Path('/data/config/runtime.json')
ENV_KEYS={'DATABASE_BOT_URL','DATABASE_WORKER_URL','DATABASE_STAFF_URL','RECRUITMENT_ID','VK_GROUP_ID'}


def load_bank():
    return json.loads((ROOT/'config/museum-bank.json').read_text(encoding='utf-8-sig'))


def runtime_environment(path=CONFIG):
    env=json.loads(path.read_text(encoding='utf-8'))['env']
    if not set(env)<=ENV_KEYS:raise ValueError('Only runtime configuration is allowed')
    return env


def save(path,config):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(config,f)
    os.replace(temporary,path)


def initialize(dsn,group,admin,path=CONFIG):
    """Only for a new, isolated database or our own previous installation."""
    if group<=0 or admin<=0:raise ValueError('VK_GROUP_ID and ADMIN_VK_ID must be positive numeric IDs')
    # A session lock protects both migrations and the final single-transaction seed.
    with psycopg.connect(dsn,autocommit=True) as c:
        c.execute('SELECT pg_advisory_lock(175091104)')
        owned=c.execute("SELECT to_regclass('gim_local.installation')").fetchone()[0]
        if not owned and c.execute('''SELECT
            EXISTS(SELECT FROM pg_namespace WHERE nspname NOT IN ('public','information_schema') AND nspname NOT LIKE 'pg_%')
            OR EXISTS(SELECT FROM pg_class WHERE relnamespace='public'::regnamespace)
            OR EXISTS(SELECT FROM pg_proc WHERE pronamespace='public'::regnamespace)
            OR EXISTS(SELECT FROM pg_type WHERE typnamespace='public'::regnamespace)
            OR EXISTS(SELECT FROM pg_extension WHERE extname<>'plpgsql')''').fetchone()[0]:
            raise ValueError('Refusing to bootstrap an existing database not created by this quickstart')
        old=c.execute('SELECT config FROM gim_local.installation WHERE singleton').fetchone()[0] if owned else None
        if old and (old['group']!=group or old['admin']!=admin):
            raise ValueError('Existing installation belongs to different VK IDs; data was not changed')
        if path.exists():
            config=json.loads(path.read_text())
        elif old:
            raise ValueError('Runtime configuration volume missing; restore it rather than overwrite existing data')
        else:
            token=uuid4().hex
            config={'installation_id':token,'group':group,'admin':admin,'env':{'VK_GROUP_ID':str(group),'RECRUITMENT_ID':str(uuid4())}}
            params=conninfo_to_dict(dsn)
            for role in ('bot','worker','staff'):
                config['env']['DATABASE_'+role.upper()+'_URL']=make_conninfo(**{**params,'user':'gim_local_'+role+'_'+token[:12],'password':secrets.token_urlsafe(32)})
            save(path,config)
        if config['group']!=group or config['admin']!=admin or (old and old['installation_id']!=config['installation_id']):
            raise ValueError('Installation/configuration mismatch; data was not changed')
        if not owned:
            with c.transaction():
                c.execute('CREATE SCHEMA gim_local')
                c.execute('REVOKE ALL ON SCHEMA gim_local FROM PUBLIC')
                c.execute('CREATE TABLE gim_local.installation(singleton boolean PRIMARY KEY CHECK(singleton),config jsonb NOT NULL,ready boolean NOT NULL DEFAULT false)')
                c.execute('INSERT INTO gim_local.installation VALUES(true,%s,false)',(Jsonb({k:config[k] for k in ('installation_id','group','admin')}),))
        migrate(dsn,ROOT/'database/supabase/migrations')
        if c.execute('SELECT ready FROM gim_local.installation').fetchone()[0]:
            runtime_environment(path)
            return
        bank=load_bank();rubric=json.loads((ROOT/'config/ranking-50-35-15.json').read_text())
        rid=config['env']['RECRUITMENT_ID']
        with c.transaction():
            for role in ('bot','worker','staff'):
                p=conninfo_to_dict(config['env']['DATABASE_'+role.upper()+'_URL'])
                c.execute(sql.SQL('CREATE ROLE {} LOGIN INHERIT PASSWORD {} IN ROLE {}').format(sql.Identifier(p['user']),sql.Literal(p['password']),sql.Identifier('gim_'+role)))
            c.execute('''INSERT INTO gim.recruitments(id,group_id,title,questionnaire_version,rubric_version,rubric,direction_info,followup_policy)
                VALUES(%s,%s,'Волонтёры ГИМ','museum-v2',%s,%s,%s,%s)''',
                (rid,group,rubric['version'],Jsonb(rubric['rubric']),Jsonb(bank['direction_info']),Jsonb({'max_followups':3,'expectations_check':True})))
            for q in bank['questions']:
                c.execute('''INSERT INTO gim.question_templates(recruitment_id,code,kind,text,position,required,target_slot,directions,validation)
                  VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(rid,q['code'],q['kind'],q['text'],q['position'],q['required'],q['target_slot'],q['directions'],Jsonb(q['validation'])))
            uid=c.execute('INSERT INTO gim.users(vk_id) VALUES(%s) RETURNING id',(admin,)).fetchone()[0]
            sid=c.execute("INSERT INTO gim.staff_members(user_id,group_id,role) VALUES(%s,%s,'admin') RETURNING id",(uid,group)).fetchone()[0]
            c.execute("INSERT INTO gim.audit_log(actor_staff_id,action) VALUES(%s,'staff.bootstrap')",(sid,))
            c.execute("UPDATE gim.recruitments SET status='active',opened_at=now() WHERE id=%s",(rid,))
            c.execute('UPDATE gim_local.installation SET ready=true')
    print('База, 18 вопросов и первый администратор готовы. Данные сохранены в Docker volumes.')


def main():
    try:
        mode=sys.argv[1] if len(sys.argv)>1 else 'run'
        if mode=='init':
            # Fixed internal Docker host: unrelated DATABASE_ADMIN_URL is intentionally ignored.
            password=os.environ['LOCAL_POSTGRES_PASSWORD']
            if len(password)<24 or password.startswith('REPLACE_'):raise ValueError('Set a unique POSTGRES_PASSWORD of at least 24 characters')
            dsn=make_conninfo(host='postgres',dbname='gim',user='postgres',password=password)
            initialize(dsn,int(os.environ['VK_GROUP_ID']),int(os.environ['ADMIN_VK_ID']))
        else:
            os.environ.update(runtime_environment())
            sys.argv=['gim.shared_main',mode]
            from gim.shared_main import main as run
            run()
    except (ValueError,KeyError,FileNotFoundError) as exc:
        # These messages are controlled locally; never include DSNs or input values.
        print('Настройка не выполнена: проверьте параметры быстрого запуска и сохранность volumes.',file=sys.stderr)
        raise SystemExit(2) from None
    except psycopg.Error:
        print('База недоступна или не прошла проверку изолированной установки. Данные не удалялись.',file=sys.stderr)
        raise SystemExit(2) from None


if __name__=='__main__':main()
