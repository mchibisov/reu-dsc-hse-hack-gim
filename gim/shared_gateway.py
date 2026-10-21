"""Durable VK ingress + fenced singleton lease; transaction-pooler compatible."""
from uuid import uuid4

from gim_db.repository import emit, one
from gim.vk import message_event
from gim.shared_export_access import seal_export


class LeaseBusy(RuntimeError):
    pass


class LeaseLost(RuntimeError):
    pass


class GatewayLedger:
    def __init__(self, pool, group_id, excel_access_code=""):
        self.pool = pool
        self.group_id = group_id
        self.excel_access_code = excel_access_code
        self.token = uuid4()

    async def acquire(self):
        async with self.pool.connection() as c:
            row = await one(c, """INSERT INTO gim.gateway_checkpoints(group_id,lease_token,lease_until)
                VALUES(%s,%s,now()+interval '90 seconds')
                ON CONFLICT(group_id) DO UPDATE SET lease_token=EXCLUDED.lease_token,
                lease_until=EXCLUDED.lease_until
                WHERE gim.gateway_checkpoints.lease_until IS NULL OR gim.gateway_checkpoints.lease_until<=now()
                RETURNING group_id""", (self.group_id, self.token))
        if not row:
            raise LeaseBusy('Другой gateway уже обрабатывает сообщество; после падения аренда истекает через 90 секунд')

    async def execute(self, _query):
        # VK.gateway guard interface. Session advisory locks do not work on transaction poolers.
        async with self.pool.connection() as c:
            row = await one(c, """UPDATE gim.gateway_checkpoints SET lease_until=now()+interval '90 seconds'
                WHERE group_id=%s AND lease_token=%s AND lease_until>now() RETURNING group_id""",
                (self.group_id, self.token))
        if not row:
            raise LeaseLost('Gateway lease lost')

    async def cursor(self, group_id):
        if group_id != self.group_id:
            raise ValueError('Group mismatch')
        async with self.pool.connection() as c:
            row = await one(c, 'SELECT ts FROM gim.gateway_checkpoints WHERE group_id=%s AND lease_token=%s AND lease_until>now()',
                            (group_id, self.token))
        if row is None:
            raise LeaseLost('Gateway lease lost')
        return row['ts']

    async def ingest_batch(self, events, group_id, next_ts):
        if group_id != self.group_id or any(e.get('group_id') != group_id for e in events):
            raise ValueError('Group mismatch')
        async with self.pool.connection() as c, c.transaction():
            row = await one(c, """SELECT group_id FROM gim.gateway_checkpoints
                WHERE group_id=%s AND lease_token=%s AND lease_until>now() FOR UPDATE""", (group_id, self.token))
            if row is None:
                raise LeaseLost('Gateway lease lost')
            await enqueue_events(c,events,group_id,self.excel_access_code)
            await c.execute("""UPDATE gim.gateway_checkpoints SET ts=%s,lease_until=now()+interval '90 seconds'
                WHERE group_id=%s AND lease_token=%s""", (str(next_ts), group_id, self.token))

    async def release(self):
        async with self.pool.connection() as c:
            row = await one(c, """UPDATE gim.gateway_checkpoints SET lease_token=NULL,lease_until=NULL
                WHERE group_id=%s AND lease_token=%s RETURNING group_id""", (self.group_id, self.token))
        return row is not None


async def enqueue_events(c,events,group_id,excel_access_code):
    """Only call after authenticating the VK transport; caller owns transaction."""
    for event in events:
        normalized = message_event(event)
        if normalized is None:
            continue
        normalized = seal_export(normalized,excel_access_code)
        actor = normalized['object']['message']['from_id']
        cmid=normalized['object']['message'].get('conversation_message_id')
        # Capture what the person could see at receipt, before queued
        # fragments can advance the worker to a different question.
        receipt=await one(c,'''SELECT a.id app_id,q.id question_id FROM gim.applications a
            JOIN gim.users u ON u.id=a.user_id JOIN gim.recruitments r ON r.id=a.recruitment_id
            LEFT JOIN LATERAL (SELECT dq.id FROM gim.dialog_questions dq WHERE dq.application_id=a.id
              AND ((dq.id=a.current_question_id AND dq.asked_at IS NOT NULL) OR dq.status='answered')
              AND (%s::bigint IS NULL OR dq.sent_cmid IS NULL OR dq.sent_cmid<%s)
              ORDER BY (dq.id=a.current_question_id) DESC,dq.position DESC LIMIT 1) q ON true
            WHERE u.vk_id=%s AND r.group_id=%s AND r.status='active' AND a.status='draft' AND NOT a.archived
            ORDER BY a.created_at DESC LIMIT 1''',(cmid,cmid,actor,group_id))
        receipt={k:str(v) if v is not None else None for k,v in receipt.items()} if receipt else {'app_id':None,'question_id':None}
        await emit(c, None, 'vk.incoming', f'vk-in:{group_id}:{normalized["event_id"]}',
                   {'event': normalized, 'group_id': group_id, 'serial_key': f'vk:{group_id}:{actor}', 'receipt':receipt})
