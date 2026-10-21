import asyncio
import contextlib
import json
import logging
import uuid
from pathlib import Path

import httpx
from psycopg.types.json import Jsonb

from gim.dialog import QUESTIONS, transition
from gim.scoring import validate_evaluation
from gim.xlsx import export_xlsx

log = logging.getLogger(__name__)
STAFF = ('curator', 'admin')


class Service:
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
        if not self.settings.consent_text:
            await self.reply(c, job, 'Приём анкет пока не открыт: куратор должен настроить текст согласия на обработку данных.')
            return
        app = await (await c.execute('SELECT * FROM applications WHERE user_id=%s AND group_id=%s AND campaign=%s FOR UPDATE',
                                    (user['id'], group, self.settings.campaign))).fetchone()
        if not app:
            app = await (await c.execute('''INSERT INTO applications(user_id,group_id,campaign,questionnaire)
                VALUES(%s,%s,%s,%s) RETURNING *''', (user['id'], group, self.settings.campaign, Jsonb(QUESTIONS)))).fetchone()
        old = app['state']
        # "Старт" during an unfinished application resumes instead of becoming an answer.
        if old.get('step') not in (None, 'submitted') and text.casefold() in ('старт', 'начать'):
            reply = self.settings.consent_text + '\nНапишите «Согласен».' if old['step'] == 'consent' else app['questionnaire'].get(old['step'], QUESTIONS.get(old['step'], ''))
            await self.reply(c, job, reply)
            return
        state, code, reply, submitted = transition(old, text)
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
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''', (app['id'], code, 'followup' if code.startswith('followup') else 'base',
                    app['questionnaire'].get(code, QUESTIONS[code]), text, revision, group, job['payload']['event_id']))
                if code == 'name':
                    await c.execute('UPDATE users SET name=%s WHERE id=%s', (text[:300], user['id']))
            await c.execute('UPDATE inbox_events SET application_id=%s WHERE group_id=%s AND event_id=%s', (app['id'], group, job['payload']['event_id']))
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

    async def command(self, c, job, user, text):
        parts = text.split(maxsplit=3)
        command = parts[0].lower()
        if command in ('/help', '/start'):
            await self.reply(c, job, 'Старт — заполнить или продолжить анкету\n/status — статус\n' + ('/top /export /stats /score /notify' if user['role'] in STAFF else 'Решение принимает куратор.'))
            return
        if command == '/status':
            row = await (await c.execute('SELECT status FROM applications WHERE user_id=%s AND group_id=%s AND campaign=%s',
                                        (user['id'], self.settings.group_id, self.settings.campaign))).fetchone()
            await self.reply(c, job, 'Статус: ' + (row['status'] if row else 'Анкета ещё не начата'))
            return
        if user['role'] not in STAFF:
            await self.reply(c, job, 'Эта команда доступна сотруднику музея.')
            return
        if command == '/notify':
            row = await (await c.execute('UPDATE users SET notify_new_applications=NOT notify_new_applications WHERE id=%s RETURNING notify_new_applications', (user['id'],))).fetchone()
            await self.reply(c, job, 'Уведомления ' + ('включены' if row['notify_new_applications'] else 'выключены'))
        elif command == '/export':
            await self.db.enqueue(c, 'export', {'peer_id': user['vk_id'], 'campaign': self.settings.campaign,
                                             'group_id': self.settings.group_id}, 'export:' + str(job['id']), recipient_id=user['id'])
            await self.reply(c, job, 'Готовлю Excel. Пришлю файл отдельным сообщением.')
        elif command in ('/top', '/stats'):
            rows = await self.rows(c)
            if command == '/stats':
                counts = {status: sum(r['status'] == status for r in rows) for status in ('draft', 'submitted', 'evaluated')}
                await self.reply(c, job, f"Всего анкет: {len(rows)}\nЧерновики: {counts['draft']}\nПоданы: {counts['submitted']}\nОценены: {counts['evaluated']}")
            else:
                lines = [f"{r['score'] if r['score'] is not None else '—'} | {r['candidate'] or 'Без имени'}\n{r['application_id']}\n{(r['summary'] or '')[:300]}" for r in rows if r['status'] != 'draft'][:10]
                await self.reply(c, job, '\n\n'.join(lines) or 'Поданных анкет пока нет.')
        elif command == '/score':
            try:
                app_id = uuid.UUID(parts[1])
                score = float(parts[2].replace(',', '.'))
                reason = parts[3].strip()
                if not 0 <= score <= 3 or not reason:
                    raise ValueError()
            except (ValueError, IndexError):
                await self.reply(c, job, 'Формат: /score ID_заявки балл_0–3 обоснование')
                return
            app = await (await c.execute("SELECT * FROM applications WHERE id=%s AND group_id=%s AND campaign=%s AND status!='draft' FOR UPDATE", (app_id, self.settings.group_id, self.settings.campaign))).fetchone()
            if not app:
                await self.reply(c, job, 'Поданная заявка этого набора не найдена.')
                return
            await c.execute('''INSERT INTO evaluations(application_id,reviewer_id,score,source,answer_revision,rubric_version,summary)
                VALUES(%s,%s,%s,'human',%s,'manual',%s)''', (app_id, user['id'], score, app['revision'], reason))
            await c.execute("UPDATE applications SET status='evaluated' WHERE id=%s", (app_id,))
            await c.execute("INSERT INTO audit_log(application_id,actor_id,action,details) VALUES(%s,%s,'manual_score',%s)", (app_id, user['id'], Jsonb({'score': score, 'reason': reason})))
            await self.reply(c, job, 'Оценка куратора сохранена отдельно от автоматической.')
        else:
            await self.reply(c, job, 'Доступно: /top /export /stats /score /notify')

    async def rows(self, c):
        return await (await c.execute('''SELECT a.id::text application_id,u.name candidate,u.vk_id,
            a.status,a.selected_directions directions,e.score::float8 score,e.summary,e.criteria_results,e.interview_questions,
            (SELECT string_agg(an.question_text || E'\n' || an.answer_text,E'\n\n' ORDER BY an.revision)
             FROM answers an WHERE an.application_id=a.id) answers
            FROM applications a JOIN users u ON u.id=a.user_id
            LEFT JOIN LATERAL (SELECT * FROM evaluations ev WHERE ev.application_id=a.id AND ev.answer_revision=a.revision
                ORDER BY (ev.source='human') DESC,ev.created_at DESC,ev.id DESC LIMIT 1) e ON true
            WHERE a.group_id=%s AND a.campaign=%s ORDER BY e.score DESC NULLS LAST,a.submitted_at,a.id''',
            (self.settings.group_id, self.settings.campaign))).fetchall()

    async def score(self, job):
        if not self.settings.scoring_url:
            raise RuntimeError('SCORING_URL_not_configured')
        app_id = job['payload']['application_id']
        async with self.db.pool.connection() as c:
            app = await (await c.execute('SELECT * FROM applications WHERE id=%s', (app_id,))).fetchone()
            answers = await (await c.execute('SELECT id::text,question_code,question_text,answer_text FROM answers WHERE application_id=%s ORDER BY revision', (app_id,))).fetchall()
        headers = {'Authorization': 'Bearer ' + self.settings.scoring_token} if self.settings.scoring_token else {}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(self.settings.scoring_url, json={
                'application_id': str(app['id']), 'answer_revision': app['revision'],
                'selected_directions': app['selected_directions'],
                'answers': [a for a in answers if a['question_code'] not in ('name', 'source')]}, headers=headers)
            response.raise_for_status()
            result = validate_evaluation(response.json(), answers)
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
        async with self.db.pool.connection() as c:
            user = await (await c.execute('SELECT * FROM users WHERE id=%s', (job['recipient_id'],))).fetchone()
            if not user or not user['active'] or user['role'] not in STAFF:
                return
            rows = await self.rows(c)
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
                (job['id'], user['id'], self.settings.campaign, name, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', len(data)))
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
                await self.vk.send(p['peer_id'], p.get('text', 'Анкеты ГИМ'), job['vk_random_id'], attachment)
        elif kind == 'score':
            await self.score(job)
        elif kind == 'export':
            await self.export(job)
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
                job = await self.db.claim()
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
