"""Operator-only provisioning. Passwords are read from a file, never CLI/history.

Input JSON: {"bot":{"login":"...","password":"..."},"worker":...,"staff":...}.
Use a private file chmod 600. Never use this against an unrelated project.
"""
import argparse
import json
import os
from pathlib import Path
import psycopg
from psycopg import sql

p=argparse.ArgumentParser();p.add_argument('credentials_file');a=p.parse_args()
config=json.loads(Path(a.credentials_file).read_text())
with psycopg.connect(os.environ['DATABASE_ADMIN_URL']) as c:
    for service in ('bot','worker','staff'):
        entry=config[service];login=entry['login'];password=entry['password']
        if not login.startswith('gim_') or len(password)<24:raise ValueError('gim_ login and >=24-character generated password required')
        # Deliberately fail if the login already exists, rather than rotate an unknown credential.
        c.execute(sql.SQL('CREATE ROLE {} LOGIN INHERIT PASSWORD {}').format(sql.Identifier(login),sql.Literal(password)))
        # Dedicated login gets a single service role. No ADMIN OPTION.
        c.execute(sql.SQL('GRANT {} TO {}').format(sql.Identifier('gim_'+service),sql.Identifier(login)))
print('Three least-privilege runtime logins created; no credentials printed')
