"""One-request Excel access; no staff role is granted and no plaintext code is stored."""
import copy
import hashlib
import hmac
import json
from uuid import UUID,uuid4
from psycopg.types.json import Jsonb
from gim_db.repository import one,emit,audit


def _proof(event, secret, argument):
    msg=event['object']['message']
    context=[event['group_id'],event['event_id'],msg['from_id'],msg['peer_id'],argument]
    return hmac.new(secret.encode(),json.dumps(context,ensure_ascii=False).encode(),hashlib.sha256).hexdigest()


def seal_export(event,secret):
    event=copy.deepcopy(event)
    msg=event['object']['message']
    parts=msg.get('text','').strip().split(maxsplit=1)
    if len(parts)!=2 or parts[0].casefold()!='/export':
        return event
    argument=parts[1].strip()
    event['_export_access']={'proof':_proof(event,secret,argument)}
    # Preserve the established staff /export UUID command, not a UUID-shaped secret.
    if argument!=secret:
        try:event['_export_access']['application_id']=str(UUID(argument))
        except ValueError:pass
    msg['text']='/export'
    return event


def valid_proof(event,secret):
    if not secret:
        return False
    supplied=event.get('_export_access',{}).get('proof','')
    return isinstance(supplied,str) and hmac.compare_digest(supplied,_proof(event,secret,secret))


# Same four-sheet snapshot as staff export, without its staff impersonation.
# Executed only by the trusted worker AFTER a verified one-request code capability.
EXPORT_QUERY = """
 WITH selected AS (
  SELECT a.*,u.vk_id,u.full_name,u.email,e.id evaluation_id,e.score,e.source evaluation_source,e.reviewer_staff_id,e.summary,
   e.recommended_directions,e.interview_questions,e.criteria_results,e.answers_revision evaluation_revision,e.created_at evaluated_at,
   reviewer.full_name reviewer_name
  FROM gim.applications a JOIN gim.users u ON u.id=a.user_id
  LEFT JOIN gim.effective_evaluations e ON e.application_id=a.id
  LEFT JOIN gim.staff_members sm ON sm.id=e.reviewer_staff_id LEFT JOIN gim.users reviewer ON reviewer.id=sm.user_id
  WHERE a.recruitment_id=%s
 ), questionnaire AS (
  SELECT id application_id,vk_id,full_name,email,birth_date,birth_date_raw,status,decision,selected_directions,undecided,
    answers_revision,submitted_at,evaluation_id,score,evaluation_source,reviewer_staff_id,reviewer_name,summary,
    recommended_directions,criteria_results,evaluation_revision,evaluated_at,
    COALESCE(evaluation_revision<answers_revision,false) evaluation_stale
  FROM selected ORDER BY score DESC NULLS LAST,submitted_at NULLS LAST,id
 ), answers AS (
  SELECT s.id application_id,q.id question_id,q.position,q.text question_text,q.source question_source,q.purpose,q.target_slot,
    a.id answer_id,a.revision,a.answer_text,a.value,a.created_at,
    a.id=(SELECT aa.id FROM gim.answers aa WHERE aa.question_id=q.id ORDER BY aa.revision DESC LIMIT 1) is_latest
  FROM selected s JOIN gim.dialog_questions q ON q.application_id=s.id LEFT JOIN gim.answers a ON a.question_id=q.id
  ORDER BY s.id,q.position,a.revision
 ), interview AS (
  SELECT id application_id,evaluation_id,summary,interview_questions,
   (SELECT COALESCE(jsonb_agg(jsonb_build_object('question',q.text,'answer',a.answer_text,'revision',a.revision) ORDER BY q.position,a.revision),'[]')
     FROM gim.dialog_questions q LEFT JOIN gim.answers a ON a.question_id=q.id WHERE q.application_id=s.id AND q.purpose='expectations') expectations
  FROM selected s ORDER BY id
 )
 SELECT jsonb_build_object('snapshot_at',transaction_timestamp(),'recruitment_id',%s,'filters','{}'::jsonb,
  'Анкеты',COALESCE((SELECT jsonb_agg(to_jsonb(q)) FROM questionnaire q),'[]'),
  'Ответы',COALESCE((SELECT jsonb_agg(to_jsonb(a)) FROM answers a),'[]'),
  'Собеседование',COALESCE((SELECT jsonb_agg(to_jsonb(i)) FROM interview i),'[]'),
  'Сводка',jsonb_build_object('total',(SELECT count(*) FROM selected),'scored',(SELECT count(score) FROM selected),
    'unscored',(SELECT count(*) FROM selected WHERE score IS NULL),'average_score',(SELECT avg(score) FROM selected),
    'score_distribution',(SELECT COALESCE(jsonb_object_agg(score,n),'{}') FROM (SELECT score,count(*) n FROM selected WHERE score IS NOT NULL GROUP BY score) x),
    'directions',(SELECT COALESCE(jsonb_object_agg(direction,n),'{}') FROM (SELECT d direction,count(*) n FROM selected,unnest(selected_directions) d GROUP BY d) x),
    'decisions',(SELECT COALESCE(jsonb_object_agg(decision,n),'{}') FROM (SELECT decision,count(*) n FROM selected GROUP BY decision) x)))
"""


async def request_code_export(service,event,actor):
    repo=service.worker_repo
    incoming=event['payload']['event']
    rid=service.settings.recruitment_id
    group=service.settings.group_id
    secret=getattr(service.settings,'excel_access_code','')
    async with repo.pool.connection() as c,c.transaction():
        await c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'export-code:{group}:{actor}',))
        old=await one(c,"SELECT action FROM gim.audit_log WHERE details->>'event_id'=%s AND action IN ('export.code.denied','export.code.requested')",(str(event['id']),))
        if old:return old['action']=='export.code.requested'
        attempts=await one(c,"""SELECT count(*) AS n FROM gim.audit_log WHERE action='export.code.denied'
            AND details->>'group_id'=%s AND details->>'vk_id'=%s AND created_at>now()-interval '10 minutes'""",(str(group),str(actor)))
        details={'event_id':str(event['id']),'group_id':group,'vk_id':actor}
        if attempts['n']>=5 or not valid_proof(incoming,secret):
            await audit(c,None,'export.code.denied',details)
            return False
        # Serialize cohort version allocation exactly as the existing staff export does.
        await c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(str(rid),))
        recruitment=await one(c,'SELECT group_id FROM gim.recruitments WHERE id=%s',(rid,))
        if not recruitment or recruitment['group_id']!=group:raise ValueError('Export scope mismatch')
        snapshot=await one(c,EXPORT_QUERY,(rid,)*EXPORT_QUERY.count('%s'))
        # The query returns one JSON expression, not raw rows from separate snapshots.
        snapshot=next(iter(snapshot.values()))
        version=await one(c,"SELECT COALESCE(max(version),0)+1 AS n FROM gim.files WHERE recruitment_id=%s AND application_id IS NULL AND kind='xlsx'",(rid,))
        fid=uuid4()
        grant={'incoming_event_id':str(event['id']),'vk_id':actor,'group_id':group}
        await c.execute("""INSERT INTO gim.files(id,recruitment_id,kind,scope,version,filters,storage_key,mime_type)
            VALUES(%s,%s,'xlsx','cohort',%s,%s,%s,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')""",
            (fid,rid,version['n'],Jsonb({'code_access':grant}),f'{rid}/{fid}'))
        await emit(c,None,'file.export','code-export:'+str(event['id']),
                   {'snapshot':snapshot,'group_id':group},file_id=fid)
        await audit(c,None,'export.code.requested',{**details,'file_id':str(fid)})
        return True


async def code_recipient(service,meta):
    grant=meta.get('filters',{}).get('code_access')
    if not grant or grant.get('group_id')!=service.settings.group_id or meta['recruitment_id']!=service.settings.recruitment_id:
        return None
    async with service.worker_repo.pool.connection() as c:
        source=await one(c,"SELECT payload FROM gim.outbox_events WHERE id=%s AND topic='vk.incoming'",(grant['incoming_event_id'],))
    if not source:return None
    event=source['payload']['event']
    if (event.get('group_id')!=grant['group_id'] or event['object']['message']['from_id']!=grant['vk_id']
        or not valid_proof(event,getattr(service.settings,'excel_access_code',''))):return None
    return grant['vk_id']
