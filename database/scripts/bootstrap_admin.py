"""Bootstrap exactly one verified first admin; subsequent membership changes use set_staff."""
import argparse
import os
import psycopg
p=argparse.ArgumentParser();p.add_argument('--group-id',type=int,required=True);p.add_argument('--verified-vk-id',type=int,required=True)
a=p.parse_args()
with psycopg.connect(os.environ['DATABASE_ADMIN_URL']) as c:
    c.execute('SELECT pg_advisory_xact_lock(%s)',(a.group_id,))
    if c.execute('SELECT 1 FROM gim.staff_members WHERE group_id=%s AND active',(a.group_id,)).fetchone():
        raise ValueError('Staff already configured; use current admin, do not bypass it')
    c.execute('INSERT INTO gim.users(vk_id) VALUES(%s) ON CONFLICT(vk_id) DO NOTHING',(a.verified_vk_id,))
    uid=c.execute('SELECT id FROM gim.users WHERE vk_id=%s',(a.verified_vk_id,)).fetchone()[0]
    sid=c.execute("INSERT INTO gim.staff_members(user_id,group_id,role) VALUES(%s,%s,'admin') RETURNING id",(uid,a.group_id)).fetchone()[0]
    c.execute("INSERT INTO gim.audit_log(actor_staff_id,action) VALUES(%s,'staff.bootstrap')",(sid,))
print('First verified administrator configured')
