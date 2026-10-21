import asyncio
import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from gim.shared_config import SharedSettings
from gim.shared_main import run

if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
DSN = os.environ.get('TEST_DATABASE_URL')


@unittest.skipUnless(DSN, 'Нужна отдельная локальная TEST_DATABASE_URL')
class BootstrapIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_check_db_with_three_real_runtime_logins(self):
        params = conninfo_to_dict(DSN)
        if params.get('host') not in {'127.0.0.1', 'localhost', '::1'}:
            self.skipTest('Только локальная тестовая БД')
        token = uuid4().hex[:10]
        group = uuid4().int % 1000000000 + 1
        logins = []
        env = {'VK_GROUP_ID': str(group)}
        with psycopg.connect(DSN, autocommit=True, row_factory=dict_row) as c:
            try:
                for role in ('bot', 'worker', 'staff'):
                    login = 'gim_smoke_' + role + '_' + token
                    password = uuid4().hex
                    c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} INHERIT IN ROLE {}').format(
                        sql.Identifier(login), sql.Literal(password), sql.Identifier('gim_' + role)))
                    logins.append(login)
                    env['DATABASE_' + role.upper() + '_URL'] = make_conninfo(**{**params, 'user': login, 'password': password})
                recruitment = c.execute("""INSERT INTO gim.recruitments(group_id,title,questionnaire_version,rubric_version,rubric)
                    VALUES(%s,'Synthetic startup','test','test',%s) RETURNING id""",
                    (group, Jsonb({'criteria': [], 'approval': 'synthetic-test-only'}))).fetchone()['id']
                for position, slot in enumerate(('consent', 'birth_date', 'directions'), 1):
                    c.execute("""INSERT INTO gim.question_templates(recruitment_id,code,kind,text,position,required,target_slot)
                        VALUES(%s,%s,'base','Synthetic',%s,true,%s)""", (recruitment, slot, position, slot))
                c.execute("UPDATE gim.recruitments SET status='active',opened_at=now() WHERE id=%s", (recruitment,))
                env['RECRUITMENT_ID'] = str(recruitment)
                with patch.dict(os.environ, env, clear=True):
                    settings = SharedSettings.load()
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    await run('check-db', settings)
                result = json.loads(output.getvalue())
                self.assertEqual(result['schema'], 'gim')
                self.assertEqual(result['base_questions'], 3)
                self.assertEqual(result['analysis'], 'disabled')
                self.assertFalse(result['redis'])
            finally:
                for login in logins:
                    c.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(login)))
