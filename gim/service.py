import asyncio
import contextlib
import logging
import uuid
from pathlib import Path

import httpx
from psycopg.types.json import Jsonb

from gim.dialog import BASE, QUESTIONS, TASKS, transition
from gim.followups import validate_decision
from gim.llm import LLMClient
from gim.rubric import load_rubric, validate_rubric_evaluation
from gim.xlsx import export_xlsx

log = logging.getLogger(__name__)
from gim.admin import StaffCommands, STAFF


class Service(StaffCommands):
    def __init__(self, db, vk, settings):
        self.db, self.vk, self.settings = db, vk, settings

    async def reply(self, c, job, text, suffix='reply', peer_id=None, recipient_id=None):
        if peer_id is None:
            peer_id = job['payload']['object']['message']['peer_id']
        if recipient_id is None:
            recipient_id = job.get('response_recipient_id')
        # VK message limit: split on paragraph boundaries with deterministic job keys.
        for index in range(0, max(1, len(text)), 3500):
            await self.db.enqueue(c, 'send', {'peer_id': peer_id, 'text': text[index:index+3500],
                'serial_key': f'send:{self.settings.group_id}:{peer_id}'},
                                  f"{job['id']}:{suffix}:{index}", recipient_id=recipient_id)

    async def dialog(self, job):
        event = job['payload']
        msg = event['object']['message']
        text = msg.get('text', '').strip()
        group = event['group_id']
        async with self.db.pool.connection() as c:
            # Serialize processing and fence a worker whose lease was already replaced.
            await c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (event['serial_key'],))
            lease = await (await c.execute('SELECT status,lease_token FROM jobs WHERE id=%s FOR UPDATE', (job['id'],))).fetchone()
            if lease['status'] != 'running' or lease['lease_token'] != job['lease_token']:
                return
            await c.execute('INSERT INTO users(vk_id) VALUES(%s) ON CONFLICT(vk_id) DO NOTHING', (msg['from_id'],))
            user = await (await c.execute('SELECT * FROM users WHERE vk_id=%s FOR UPDATE', (msg['from_id'],))).fetchone()
            if not user['active']:
                await c.execute("UPDATE jobs SET status='done',lease_until=NULL WHERE id=%s", (job['id'],))
                return
            if text.startswith('/'):
                if user['role'] in STAFF:
                    job['response_recipient_id'] = user['id']
                await self.command(c, job, user, text)
            elif text.casefold() in ('помощь', 'меню'):
                commands = 'Старт — заполнить анкету\n/status — статус\n/help — помощь'
                if user['role'] in STAFF:
                    commands += '\n/top — рейтинг\n/export — Excel\n/stats — сводка\n/score ID 0–3 причина — оценка куратора\n/notify — уведомления'
                await self.reply(c, job, commands)
            else:
                await self.answer(c, job, user, text, group)
            await c.execute("UPDATE jobs SET status='done',lease_until=NULL WHERE id=%s", (job['id'],))

    async def answer(self, c, job, user, text, group):
        if getattr(self.settings, 'test_mode', False) and user['vk_id'] not in self.settings.admin_ids:
            await self.reply(c, job, 'Сейчас бот проходит тестирование. Приём анкет ещё не открыт.')
            return
        app = await (await c.execute('SELECT * FROM applications WHERE user_id=%s AND group_id=%s AND campaign=%s FOR UPDATE',
                                    (user['id'], group, self.settings.campaign))).fetchone()
        if not app:
            app = await (await c.execute('''INSERT INTO applications(user_id,group_id,campaign,questionnaire)
                VALUES(%s,%s,%s,%s) RETURNING *''', (user['id'], group, self.settings.campaign,
                    Jsonb({**QUESTIONS, '_base_codes': BASE, '_tasks': TASKS,
                           '_max_followups': getattr(self.settings, 'max_followups', 3)})))).fetchone()
        old = {**app['state'], 'questions': {**app['questionnaire'], **app['state'].get('questions', {})},
               'base_codes': app['questionnaire'].get('_base_codes', BASE), 'tasks': app['questionnaire'].get('_tasks', TASKS)}
        old['max_followups'] = app['questionnaire'].get('_max_followups', getattr(self.settings, 'max_followups', 3))
        if not self.settings.consent_text or app['consent_at'] is not None:
            for attachment in job['payload']['object']['message'].get('attachments', []):
                doc = attachment.get('doc') if attachment.get('type') == 'doc' else None
                if not doc or not isinstance(doc.get('id'), int) or not isinstance(doc.get('owner_id'), int):
                    continue
                reference = f"doc{doc['owner_id']}_{doc['id']}" + ('_' + doc['access_key'] if doc.get('access_key') else '')
                file_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{app['id']}:{reference}")
                await c.execute('''INSERT INTO files(id,application_id,requested_by,kind,scope,status,storage_key,size_bytes,filters)
                    VALUES(%s,%s,%s,'resume','application','ready',%s,%s,%s) ON CONFLICT(id) DO NOTHING''',
                    (file_id, app['id'], user['id'], 'vk:' + reference, doc.get('size'), Jsonb({'title': str(doc.get('title', 'Документ'))[:300]})))
        # "Старт" during an unfinished application resumes instead of becoming an answer.
        if old.get('step') not in (None, 'submitted') and text.casefold() in ('старт', 'начать'):
            reply = (self.settings.consent_text + '\nНапишите «Согласен».' if old['step'] == 'consent'
                     else 'Готовлю следующий вопрос по вашим ответам.' if old['step'] == 'planning'
                     else app['questionnaire'].get(old['step'], QUESTIONS.get(old['step'], '')))
            await self.reply(c, job, reply)
            return
        state, code, reply, submitted = transition(old, text, require_consent=bool(self.settings.consent_text))
        if old.get('step') == 'planning' and text and len(text) <= 10000:
            code = 'supplement_ai_' + str(app['revision'] + 1)
        if state['step'] == 'consent':
            reply = self.settings.consent_text + '\n\n' + reply
        revision = app['revision']
        if code:
            if code == 'consent':
                await c.execute('UPDATE applications SET consent_at=now() WHERE id=%s', (app['id'],))
                await c.execute("INSERT INTO audit_log(application_id,actor_id,action) VALUES(%s,%s,'consent')", (app['id'], user['id']))
            else:
                revision += 1
                await c.execute('''INSERT INTO answers(application_id,question_code,question_kind,question_text,answer_text,revision,group_id,event_id)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''', (app['id'], code,
                    'followup' if code.startswith('followup') else 'supplement' if code.startswith('supplement') else 'base',
                    app['questionnaire'].get(code, QUESTIONS.get(code, 'Дополнение кандидата')), text, revision, group, job['payload']['event_id']))
                await c.execute('UPDATE applications SET profile=profile || %s WHERE id=%s', (Jsonb({code: text}), app['id']))
                if code == 'name':
                    await c.execute('UPDATE users SET name=%s WHERE id=%s', (text[:300], user['id']))
            await c.execute('UPDATE inbox_events SET application_id=%s WHERE group_id=%s AND event_id=%s', (app['id'], group, job['payload']['event_id']))
        if code and (code == 'source' or code.startswith(('followup_', 'supplement_'))):
            if state.get('followup_count', 0) >= state['max_followups']:
                state['step'] = 'expectations'
                reply = self.expectations_reply(state)
            else:
                state['step'] = 'planning'
                await self.db.enqueue(c, 'prepare_followups', {'application_id': str(app['id']), 'revision': revision,
                    'peer_id': user['vk_id'], 'serial_key': f"ai:{group}:{app['id']}"},
                    f"followups:{app['id']}:{revision}", application_id=app['id'])
                reply = 'Ответ сохранён. Анализирую анкету и выбираю следующий уточняющий вопрос.'
        await c.execute('''UPDATE applications SET state=%s,revision=%s,selected_directions=%s,
            status=CASE WHEN %s THEN 'submitted' ELSE status END,
            submitted_at=CASE WHEN %s THEN now() ELSE submitted_at END WHERE id=%s''',
            (Jsonb(state), revision, state.get('directions', []), submitted, submitted, app['id']))
        await self.reply(c, job, reply)
        if submitted:
            await self.db.enqueue(c, 'score', {'application_id': str(app['id']), 'revision': revision}, f"score:{app['id']}:{revision}", application_id=app['id'])
            await c.execute("INSERT INTO audit_log(application_id,actor_id,action) VALUES(%s,%s,'submitted')", (app['id'], user['id']))
            staff = await (await c.execute("SELECT * FROM users WHERE active AND role IN ('curator','admin') AND notify_new_applications")).fetchall()
            for recipient in staff:
                await self.reply(c, job, '+1 заполненная заявка\nID: ' + str(app['id']), 'notify:' + str(recipient['id']), recipient['vk_id'], recipient['id'])

    @staticmethod
    def expectations_reply(state):
        return '\n'.join(state.get('tasks', TASKS)[d] for d in state.get('directions', [])) + '\n\n' + state.get('questions', {}).get('expectations', QUESTIONS['expectations'])

    async def prepare_followups(self, job):
        app_id = job['payload']['application_id']
        async with self.db.pool.connection() as c:
            if not await self.owns_lease(c, job):
                return
            app = await (await c.execute('SELECT * FROM applications WHERE id=%s', (app_id,))).fetchone()
            if app and 'revision' not in job['payload']:
                # Jobs queued by the previous bot version did not contain a revision.
                job['payload']['revision'] = app['revision']
                await c.execute('UPDATE jobs SET payload=payload || %s WHERE id=%s',
                    (Jsonb({'revision': app['revision']}), job['id']))
            answers = await (await c.execute("SELECT id::text,revision,question_code,question_kind,question_text,answer_text FROM answers WHERE application_id=%s AND question_code NOT IN ('name','source') ORDER BY revision", (app_id,))).fetchall()
        if not app or app['state'].get('step') != 'planning' or app['revision'] != job['payload']['revision']:
            return
        maximum = app['state'].get('max_followups', app['questionnaire'].get('_max_followups', getattr(self.settings, 'max_followups', 3)))
        remaining = maximum - app['state'].get('followup_count', 0)
        if remaining <= 0:
            decision = {'action': 'finish'}
        elif getattr(self.settings, 'followup_url', ''):
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(self.settings.followup_url, json={
                    'application_id': str(app['id']), 'answer_revision': app['revision'],
                    'selected_directions': app['selected_directions'], 'answers': answers,
                    'direction_tasks': app['state'].get('tasks', TASKS), 'remaining_questions': remaining},
                    headers={'Authorization': 'Bearer ' + self.settings.service_token} if self.settings.service_token else {})
                response.raise_for_status()
                decision = response.json()
        else:
            decision = await LLMClient(self.settings).next_question(answers, app['selected_directions'], remaining)
        decision = validate_decision(decision, app['selected_directions'], [a['question_text'] for a in answers])
        async with self.db.pool.connection() as c:
            # Serialize publication with incoming event ingestion and dialog processing.
            serial_key = f"{app['group_id']}:{job['payload']['peer_id']}"
            await c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (serial_key,))
            if not await self.owns_lease(c, job):
                return
            current = await (await c.execute('SELECT state,revision FROM applications WHERE id=%s FOR UPDATE', (app_id,))).fetchone()
            if current['state'].get('step') != 'planning' or current['revision'] != job['payload']['revision']:
                return
            pending = await (await c.execute("""SELECT id FROM jobs WHERE kind='dialog'
                AND payload->>'serial_key'=%s AND status IN ('pending','running') LIMIT 1""", (serial_key,))).fetchone()
            if pending:
                # Let queued additions become answers before asking the model again.
                raise RuntimeError('Incoming answers are awaiting persistence')
            state = dict(current['state'])
            state['max_followups'] = maximum
            questions = {}
            if decision['action'] == 'finish':
                state['step'] = 'expectations'
                text = self.expectations_reply(state)
            else:
                count = state.get('followup_count', 0) + 1
                code = 'followup_ai_' + str(count)
                state.update(step=code, followup_count=count)
                questions[code] = decision['question']
                state['questions'] = {**state.get('questions', {}), **questions}
                text = decision['question']
            await c.execute('UPDATE applications SET state=%s,questionnaire=questionnaire || %s WHERE id=%s', (Jsonb(state), Jsonb(questions), app_id))
            await c.execute("INSERT INTO audit_log(application_id,action,details) VALUES(%s,'ai_next_question',%s)",
                (app_id, Jsonb({'action': decision['action'], 'answer_revision': current['revision'], 'direction': decision.get('direction')})))
            await self.reply(c, job, text, peer_id=job['payload']['peer_id'])

    async def score(self, job):
        app_id = job['payload']['application_id']
        async with self.db.pool.connection() as c:
            app = await (await c.execute('SELECT * FROM applications WHERE id=%s', (app_id,))).fetchone()
            answers = await (await c.execute('SELECT id::text,question_code,question_text,answer_text FROM answers WHERE application_id=%s ORDER BY revision', (app_id,))).fetchall()
        visible_answers = [a for a in answers if a['question_code'] not in ('name', 'source')]
        rubric = job['payload'].get('rubric') or load_rubric(getattr(self.settings, 'rubric_path', ''))
        # The team endpoint and direct provider use the same frozen, human-authored rubric.
        async with self.db.pool.connection() as c:
            if not await self.owns_lease(c, job):
                return
            await c.execute("UPDATE jobs SET payload=payload || %s WHERE id=%s", (Jsonb({'rubric': rubric}), job['id']))
        if self.settings.scoring_url:
            headers = {'Authorization': 'Bearer ' + self.settings.scoring_token} if self.settings.scoring_token else {}
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(self.settings.scoring_url, json={
                    'application_id': str(app['id']), 'answer_revision': app['revision'],
                    'selected_directions': app['selected_directions'], 'answers': visible_answers, 'rubric': rubric}, headers=headers)
                response.raise_for_status()
                result = validate_rubric_evaluation(response.json(), rubric, visible_answers)
        else:
            raw = await LLMClient(self.settings).evaluate(visible_answers, app['selected_directions'], rubric)
            result = validate_rubric_evaluation(raw, rubric, visible_answers)
        async with self.db.pool.connection() as c:
            if not await self.owns_lease(c, job):
                return
            current = await (await c.execute('SELECT revision FROM applications WHERE id=%s FOR UPDATE', (app_id,))).fetchone()
            if current['revision'] != job['payload']['revision']:
                return
            # A retry after a crash must not create a second model evaluation.
            exists = await (await c.execute("SELECT id FROM evaluations WHERE application_id=%s AND answer_revision=%s AND source='model'", (app_id, current['revision']))).fetchone()
            if exists:
                return
            await c.execute('''INSERT INTO evaluations(application_id,score,source,answer_revision,rubric_version,rubric_snapshot,
                criteria_results,summary,interview_questions,recommended_directions)
                VALUES(%s,%s,'model',%s,%s,%s,%s,%s,%s,%s)''', (app_id, result['score'], current['revision'], result['rubric_version'],
                Jsonb(result['rubric_snapshot']), Jsonb(result['criteria_results']), result['summary'], Jsonb(result['interview_questions']), result['recommended_directions']))
            await c.execute("UPDATE applications SET status='evaluated' WHERE id=%s", (app_id,))

    async def export(self, job):
        campaign = job['payload'].get('campaign', self.settings.campaign)
        async with self.db.pool.connection() as c:
            user = await (await c.execute('SELECT * FROM users WHERE id=%s', (job['recipient_id'],))).fetchone()
            if not user or not user['active'] or user['role'] not in STAFF:
                return
            existing = await (await c.execute("SELECT id FROM files WHERE id=%s AND status='ready'", (job['id'],))).fetchone()
            if existing:
                return
            rows = await self.rows(c, campaign=campaign)
        data = await asyncio.to_thread(export_xlsx, rows)
        storage = Path(self.settings.storage_dir)
        storage.mkdir(parents=True, exist_ok=True)
        name = f"applications-{job['id']}-{job['lease_token']}.xlsx"
        path = storage / name
        await asyncio.to_thread(path.write_bytes, data)
        async with self.db.pool.connection() as c:
            if not await self.owns_lease(c, job):
                path.unlink(missing_ok=True)
                return
            # File id derives from job id so retrying export updates metadata atomically.
            await c.execute('''INSERT INTO files(id,requested_by,kind,scope,status,campaign,snapshot_at,storage_key,mime_type,size_bytes)
                VALUES(%s,%s,'xlsx','campaign','ready',%s,now(),%s,%s,%s)
                ON CONFLICT(id) DO UPDATE SET status='ready',size_bytes=EXCLUDED.size_bytes''',
                (job['id'], user['id'], campaign, name, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', len(data)))
            await self.db.enqueue(c, 'send_file', {'peer_id': user['vk_id'], 'storage_key': name,
                'serial_key': f'send:{self.settings.group_id}:{user["vk_id"]}'}, 'file:' + str(job['id']), recipient_id=user['id'], file_id=job['id'])

    async def owns_lease(self, c, job):
        row = await (await c.execute('SELECT status,lease_token FROM jobs WHERE id=%s FOR UPDATE', (job['id'],))).fetchone()
        return bool(row and row['status'] == 'running' and row['lease_token'] == job['lease_token'])

    async def handle(self, job):
        kind = job['kind']
        if kind == 'dialog':
            await self.dialog(job)
        elif kind in ('send', 'send_file'):
            async with self.db.pool.connection() as c:
                if not await self.owns_lease(c, job):
                    return
                if job['recipient_id']:
                    user = await (await c.execute('SELECT active,role FROM users WHERE id=%s FOR SHARE', (job['recipient_id'],))).fetchone()
                    if not user or not user['active'] or user['role'] not in STAFF:
                        return
                p = job['payload']
                attachment = None
                if kind == 'send_file':
                    path = Path(self.settings.storage_dir) / p['storage_key']
                    data = await asyncio.to_thread(path.read_bytes)
                    attachment = await self.vk.upload(p['peer_id'], path.name, data)
                role = user['role'] if job['recipient_id'] else 'candidate'
                await self.vk.send(p['peer_id'], p.get('text', 'Анкеты ГИМ'), job['vk_random_id'], attachment, role=role)
        elif kind == 'score':
            await self.score(job)
        elif kind == 'export':
            await self.export(job)
        elif kind == 'prepare_followups':
            await self.prepare_followups(job)
        else:
            raise RuntimeError('Unsupported_job_kind')

    async def heartbeat(self, job):
        while True:
            await asyncio.sleep(25)
            if not await self.db.renew(job):
                return

    async def worker(self):
        while True:
            job = None
            try:
                job = await self.db.claim(kinds=self.settings.job_kinds or None, group_id=self.settings.group_id)
                if not job:
                    await asyncio.sleep(0.5)
                    continue
                beat = asyncio.create_task(self.heartbeat(job))
                try:
                    await self.handle(job)
                    if job['kind'] != 'dialog':
                        await self.db.finish(job)
                finally:
                    beat.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await beat
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Avoid logging free answers, tokens, URLs, or HTTP bodies.
                log.error('worker error_type=%s job_id=%s kind=%s', type(exc).__name__, job['id'] if job else None, job['kind'] if job else None)
                if job:
                    await self.db.finish(job, type(exc).__name__)
                await asyncio.sleep(1)
