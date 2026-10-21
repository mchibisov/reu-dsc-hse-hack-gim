"""Trusted server contract; VK identities MUST come from verified server sessions.

Never pass client-provided role/group/actor fields as authorization. Each method
commits its own short transaction. Do not hold a connection while calling LLM/VK.
"""
import hashlib
import json
from datetime import date
from uuid import UUID
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row


class Conflict(ValueError):
    """Re-read dialog context; never silently assign an answer to another question."""


def create_pool(dsn: str, *, max_size: int = 5) -> AsyncConnectionPool:
    return AsyncConnectionPool(dsn, min_size=1, max_size=max_size, open=False,
        kwargs={'autocommit': True, 'row_factory': dict_row, 'prepare_threshold': None,
                'application_name': 'gim-db', 'connect_timeout': 10})


async def one(c, query, args=()):
    return await (await c.execute(query,args)).fetchone()


async def all_rows(c, query, args=()):
    return await (await c.execute(query,args)).fetchall()


async def app_lock(c, app_id):
    a = await one(c,'SELECT * FROM gim.applications WHERE id=%s FOR UPDATE',(app_id,))
    if not a:
        raise LookupError('Application not found')
    return a


def check_revision(a, revision):
    if a['answers_revision'] != revision:
        raise Conflict('Stale data revision')


async def emit(c, app_id, topic, key, payload=None, staff_id=None, file_id=None):
    return await one(c,'''INSERT INTO gim.outbox_events(application_id,topic,dedupe_key,payload,recipient_staff_id,file_id)
       VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(dedupe_key) DO NOTHING RETURNING *''',
       (app_id,topic,key,Jsonb(payload or {}),staff_id,file_id))


async def audit(c, app_id, action, details=None):
    await c.execute('INSERT INTO gim.audit_log(application_id,action,details) VALUES(%s,%s,%s)',
                    (app_id,action,Jsonb(details or {})))


class Repository:
    def __init__(self, pool):
        self.pool = pool

    async def start_application(self, recruitment_id: UUID, verified_vk_id: int):
        async with self.pool.connection() as c, c.transaction():
            r = await one(c,"SELECT * FROM gim.recruitments WHERE id=%s AND status='active'",(recruitment_id,))
            if not r: raise Conflict('Recruitment not active')
            # Avoid granting UPDATE(vk_id) to runtime merely for an upsert.
            await c.execute('INSERT INTO gim.users(vk_id) VALUES(%s) ON CONFLICT(vk_id) DO NOTHING',(verified_vk_id,))
            u=await one(c,'SELECT id FROM gim.users WHERE vk_id=%s',(verified_vk_id,))
            await c.execute('INSERT INTO gim.applications(user_id,recruitment_id) VALUES(%s,%s) ON CONFLICT(user_id,recruitment_id) DO NOTHING',(u['id'],recruitment_id))
            return await one(c,'SELECT * FROM gim.applications WHERE user_id=%s AND recruitment_id=%s',(u['id'],recruitment_id))

    async def set_consent(self, app_id, version: str):
        if not version.strip(): raise ValueError('Consent version required')
        async with self.pool.connection() as c, c.transaction():
            a=await app_lock(c,app_id)
            if a['status']!='draft': raise Conflict('Application not editable')
            if a['consent_version']==version: return
            await c.execute('UPDATE gim.applications SET consent_version=%s,consent_at=now(),updated_at=now() WHERE id=%s',(version,app_id))
            await audit(c,app_id,'consent.recorded',{'version':version})

    async def set_profile(self, app_id, *, expected_revision: int, birth_date: date | None,
                          selected_directions: list[str], undecided: bool, facts: dict,
                          birth_date_raw: str | None=None, birth_date_answer_id=None):
        async with self.pool.connection() as c, c.transaction():
            a=await app_lock(c,app_id); check_revision(a,expected_revision)
            if a['status']!='draft': raise Conflict('Application not editable')
            # Facts are derived from answers, never future volunteer activity.
            for fact in facts.values():
                if not isinstance(fact,dict) or not fact.get('answer_ids'): raise ValueError('Fact needs answer provenance')
                for answer_id in fact['answer_ids']:
                    if not await one(c,'SELECT 1 FROM gim.answers WHERE id=%s AND application_id=%s AND revision<=%s',(answer_id,app_id,expected_revision)):
                        raise ValueError('Foreign fact source')
            await c.execute('''UPDATE gim.applications SET birth_date=%s,birth_date_raw=%s,birth_date_answer_id=%s,
                selected_directions=%s,undecided=%s,profile=%s,updated_at=now() WHERE id=%s''',
                (birth_date,birth_date_raw,birth_date_answer_id,selected_directions,undecided,Jsonb(facts),app_id))

    async def dialog_context(self, app_id):
        async with self.pool.connection() as c, c.transaction():
            await c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            a=await one(c,'SELECT * FROM gim.applications WHERE id=%s',(app_id,))
            if not a: raise LookupError('Application not found')
            r=await one(c,'SELECT * FROM gim.recruitments WHERE id=%s',(a['recruitment_id'],))
            questions=await all_rows(c,'SELECT * FROM gim.dialog_questions WHERE application_id=%s ORDER BY position',(app_id,))
            answers=await all_rows(c,'SELECT * FROM gim.answers WHERE application_id=%s ORDER BY revision',(app_id,))
            templates=await all_rows(c,'SELECT * FROM gim.question_templates WHERE recruitment_id=%s ORDER BY position',(a['recruitment_id'],))
            return {'application':a,'questions':questions,'answers':answers,'templates':templates,
                'known_facts':a['profile'],'direction_info':r['direction_info'],'followup_policy':r['followup_policy']}

    async def prepare_question(self, app_id, *, request_key: str, expected_revision: int,
            template_id=None, text: str | None=None, target_slot: str | None=None,
            purpose='collect', context: dict | None=None, parent_question_id=None):
        async with self.pool.connection() as c, c.transaction():
            a=await app_lock(c,app_id)
            old=await one(c,'SELECT * FROM gim.dialog_questions WHERE application_id=%s AND request_key=%s',(app_id,request_key))
            if old: return old  # Persisted wording wins after restart, even if regenerated text differs.
            check_revision(a,expected_revision)
            if a['status']!='draft': raise Conflict('Application not editable')
            if a['current_question_id'] is not None: raise Conflict('Answer current question first')
            source='generated'
            if template_id:
                t=await one(c,'SELECT * FROM gim.question_templates WHERE id=%s AND recruitment_id=%s',(template_id,a['recruitment_id']))
                if not t: raise ValueError('Foreign question template')
                source='base' if t['kind']=='base' else 'template'
                if source=='base' or text is None: text=t['text']
                target_slot=t['target_slot']
            if not text or not text.strip() or not target_slot: raise ValueError('Question wording and slot required')
            r=await one(c,'SELECT followup_policy FROM gim.recruitments WHERE id=%s',(a['recruitment_id'],))
            if source!='base':
                count=await one(c,"SELECT count(*) AS n FROM gim.dialog_questions WHERE application_id=%s AND source<>'base'",(app_id,))
                if count['n']>=r['followup_policy'].get('max_followups',5): raise Conflict('Followup limit reached')
                if parent_question_id is None and await one(c,'SELECT 1 FROM gim.dialog_questions WHERE application_id=%s AND target_slot=%s',(app_id,target_slot)):
                    raise Conflict('Slot already asked; explicit clarification parent required')
            context=context or {}
            for answer_id in context.get('answer_ids',[]):
                if not await one(c,'SELECT 1 FROM gim.answers WHERE application_id=%s AND id=%s AND revision<=%s',(app_id,answer_id,expected_revision)):
                    raise ValueError('Foreign generation context')
            pos=await one(c,'SELECT COALESCE(max(position),0)+1 AS n FROM gim.dialog_questions WHERE application_id=%s',(app_id,))
            q=await one(c,'''INSERT INTO gim.dialog_questions(application_id,template_id,source,purpose,text,target_slot,position,
                 based_on_revision,context,request_key,parent_question_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
                (app_id,template_id,source,purpose,text,target_slot,pos['n'],expected_revision,Jsonb(context),request_key,parent_question_id))
            await c.execute('UPDATE gim.applications SET current_question_id=%s,updated_at=now() WHERE id=%s',(q['id'],app_id))
            await emit(c,app_id,'question.send',f'question:{q["id"]}',{'question_id':str(q['id'])})
            return q

    async def record_answer(self, app_id, question_id, *, group_id: int, event_id: str,
                            text: str, expected_revision: int, value=None):
        if not text.strip(): raise ValueError('Empty answer')
        fingerprint=hashlib.sha256(json.dumps([str(app_id),str(question_id),text,value],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        async with self.pool.connection() as c, c.transaction():
            a=await app_lock(c,app_id)
            await c.execute('''INSERT INTO gim.inbox_events(group_id,event_id,application_id,fingerprint) VALUES(%s,%s,%s,%s)
                ON CONFLICT(group_id,event_id) DO NOTHING''',(group_id,event_id,app_id,fingerprint))
            event=await one(c,'SELECT * FROM gim.inbox_events WHERE group_id=%s AND event_id=%s',(group_id,event_id))
            if event['application_id']!=UUID(str(app_id)) or event['fingerprint']!=fingerprint: raise Conflict('VK event key reused with different content')
            old=await one(c,'SELECT * FROM gim.answers WHERE group_id=%s AND event_id=%s',(group_id,event_id))
            if old: return old
            check_revision(a,expected_revision)
            q=await one(c,'SELECT * FROM gim.dialog_questions WHERE id=%s AND application_id=%s',(question_id,app_id))
            if not q or q['status'] not in ('active','answered'): raise Conflict('Question not answerable')
            # Answered question means an explicit edit of this known question, not a new dialog turn.
            ans=await one(c,'''INSERT INTO gim.answers(application_id,question_id,revision,answer_text,value,group_id,event_id)
                VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *''',(app_id,question_id,expected_revision+1,text,Jsonb(value),group_id,event_id))
            if q['status']=='active':
                await c.execute("UPDATE gim.dialog_questions SET status='answered' WHERE id=%s",(question_id,))
                await c.execute('UPDATE gim.applications SET current_question_id=NULL WHERE id=%s',(app_id,))
            await audit(c,app_id,'answer.recorded',{'answer_id':str(ans['id']),'revision':ans['revision']})
            return ans

    async def submit(self, app_id):
        async with self.pool.connection() as c, c.transaction():
            a=await app_lock(c,app_id)
            if a['status']=='submitted': return a
            await c.execute("UPDATE gim.applications SET status='submitted',submitted_at=now(),updated_at=now() WHERE id=%s",(app_id,))
            return await one(c,'SELECT * FROM gim.applications WHERE id=%s',(app_id,))

    async def evaluation_snapshot(self, app_id, *, revision=None):
        async with self.pool.connection() as c, c.transaction():
            await c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            a=await one(c,'SELECT * FROM gim.applications WHERE id=%s',(app_id,))
            if not a: raise LookupError('Application not found')
            revision=a['answers_revision'] if revision is None else revision
            if not 0<=revision<=a['answers_revision']: raise ValueError('Invalid snapshot revision')
            r=await one(c,'SELECT rubric,rubric_version FROM gim.recruitments WHERE id=%s',(a['recruitment_id'],))
            snapshot=await one(c,'SELECT gim.snapshot(%s,%s) AS data',(app_id,revision))
            answers=await all_rows(c,'''SELECT a.id,a.question_id,a.revision,a.answer_text,a.value,
                CASE WHEN q.source='base' THEN q.target_slot ELSE 'clarification_'||q.position::text END AS target_slot
                FROM gim.answers a JOIN gim.dialog_questions q ON q.id=a.question_id
                WHERE a.id=ANY(%s::uuid[]) ORDER BY a.revision''',(snapshot['data']['answer_ids'],))
            files=await all_rows(c,'SELECT id,sha256,extracted_text,extraction_version FROM gim.files WHERE id=ANY(%s::uuid[])',([f['id'] for f in snapshot['data']['files']],))
            return {'input_snapshot':snapshot['data'],**r,'answers':answers,'files':files}

    async def save_evaluation(self, app_id, *, snapshot, score: int, criteria: list, summary: str,
             request_key: str, directions=None, interview_questions=None, model=None,prompt_version=None,source_event_id=None,
             source_lease_token=None):
        async with self.pool.connection() as c, c.transaction():
            if source_lease_token is not None:
                event=await one(c,'''SELECT id FROM gim.outbox_events WHERE id=%s AND lease_token=%s
                    AND lease_until>now() AND completed_at IS NULL AND failed_at IS NULL
                    FOR UPDATE''',(source_event_id,source_lease_token))
                if event is None:
                    raise Conflict('Outbox lease no longer owned')
            await app_lock(c,app_id)
            # Do not even attempt a conflicting insert: triggers validate before ON CONFLICT.
            old=await one(c,"SELECT id FROM gim.evaluations WHERE application_id=%s AND source='algorithm' AND request_key=%s",(app_id,request_key))
            if old: return old['id']
            row=await one(c,'''INSERT INTO gim.evaluations(application_id,answers_revision,source,score,rubric_version,rubric_snapshot,
                criteria_results,input_snapshot,summary,recommended_directions,interview_questions,model,prompt_version,request_key,source_event_id)
                VALUES(%s,%s,'algorithm',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                (app_id,snapshot['input_snapshot']['revision'],score,snapshot['rubric_version'],Jsonb(snapshot['rubric']),Jsonb(criteria),
                 Jsonb(snapshot['input_snapshot']),summary,directions or [],Jsonb(interview_questions or []),model,prompt_version,request_key,source_event_id))
            if source_event_id:
                await c.execute('UPDATE gim.outbox_events SET completed_at=now(),last_error_code=NULL,lease_token=NULL,lease_until=NULL WHERE id=%s',(source_event_id,))
            await audit(c,app_id,'evaluation.algorithm',{'evaluation_id':str(row['id']),'revision':snapshot['input_snapshot']['revision']})
            return row['id']

    async def curator_evaluation(self, verified_vk_id, app_id, *, revision,score,criteria,summary,request_key,directions=None,interview_questions=None):
        async with self.pool.connection() as c:
            row=await one(c,'SELECT gim.curator_evaluation(%s,%s,%s,%s::smallint,%s,%s,%s::text[],%s,%s) AS id',
                (verified_vk_id,app_id,revision,score,Jsonb(criteria),summary,directions or [],Jsonb(interview_questions or []),request_key))
            return row['id']

    async def export_bundle(self, verified_vk_id, recruitment_id, *, application_id=None, filters=None):
        async with self.pool.connection() as c, c.transaction():
            await c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            row=await one(c,'SELECT gim.export_bundle(%s,%s,%s,%s) AS data',(verified_vk_id,recruitment_id,application_id,Jsonb(filters or {})))
            return row['data']

    async def notification_allowed(self, staff_id, app_id):
        async with self.pool.connection() as c:
            row=await one(c,'''SELECT EXISTS(SELECT FROM gim.staff_members s JOIN gim.recruitments r ON r.group_id=s.group_id
              JOIN gim.applications a ON a.recruitment_id=r.id WHERE s.id=%s AND a.id=%s AND s.active AND s.notify_new_applications) AS allowed''',(staff_id,app_id))
            return row['allowed']

    async def request_export(self, verified_vk_id,recruitment_id,*,application_id=None,kind='xlsx',filters=None,request_key):
        async with self.pool.connection() as c:
            row=await one(c,'SELECT gim.request_export(%s,%s,%s,%s,%s,%s) AS id',(verified_vk_id,recruitment_id,application_id,kind,Jsonb(filters or {}),request_key))
            return row['id']

    async def staff_file(self,verified_vk_id,file_id):
        async with self.pool.connection() as c:
            row=await one(c,'SELECT gim.staff_file(%s,%s) AS data',(verified_vk_id,file_id))
            return row['data']

    async def decide(self,verified_vk_id,app_id,decision):
        async with self.pool.connection() as c:
            await c.execute('SELECT gim.staff_decision(%s,%s,%s)',(verified_vk_id,app_id,decision))

    async def set_staff(self,verified_vk_id,group_id,target_vk_id,*,role='curator',active=True,notify=True):
        async with self.pool.connection() as c:
            row=await one(c,'SELECT gim.set_staff(%s,%s,%s,%s,%s,%s) AS id',(verified_vk_id,group_id,target_vk_id,role,active,notify))
            return row['id']

    async def set_contacts(self,verified_vk_id,*,full_name,email):
        """Only after consent; caller has authenticated this VK identity."""
        if not full_name.strip() or '@' not in email:raise ValueError('Full name and valid email required')
        async with self.pool.connection() as c:
            row=await one(c,'UPDATE gim.users SET full_name=%s,email=%s WHERE vk_id=%s RETURNING id',(full_name,email,verified_vk_id))
            if row is None:raise LookupError('User not found')
            return row['id']
