import uuid
from psycopg.types.json import Jsonb

STAFF = ("curator", "admin")


class StaffCommands:
    async def command(self, c, job, user, text):
        parts = text.split(maxsplit=3)
        command = parts[0].lower()
        if command == '/start':
            await self.answer(c, job, user, 'Старт', self.settings.group_id)
            return
        if command == '/whoami':
            await self.reply(c, job, f"Ваш VK ID: {user['vk_id']}\nРоль: {user['role']}")
            return
        if command == '/help':
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
        elif command == '/jobs':
            rows = await (await c.execute('''SELECT j.id,j.kind,j.status,j.attempts,j.last_error FROM jobs j
                LEFT JOIN applications a ON a.id=j.application_id
                WHERE (j.payload->>'group_id'=%s OR a.group_id=%s) AND j.status!='done'
                ORDER BY j.sequence DESC LIMIT 15''', (str(self.settings.group_id), self.settings.group_id))).fetchall()
            await self.reply(c, job, '\n'.join(f"{r['id']}\n{r['kind']}: {r['status']}, попыток {r['attempts']}" for r in rows) or 'Незавершённых задач нет.')
        elif command == '/retry':
            try:
                jid = uuid.UUID(parts[1])
            except (IndexError, ValueError):
                await self.reply(c, job, 'Формат: /retry UUID_задачи')
                return
            row = await (await c.execute('''UPDATE jobs j SET status='pending',attempts=0,available_at=now(),lease_until=NULL,lease_token=NULL
                WHERE id=%s AND status='failed' AND kind IN ('score','export','prepare_followups')
                  AND (payload->>'group_id'=%s OR EXISTS(SELECT 1 FROM applications a WHERE a.id=j.application_id AND a.group_id=%s))
                RETURNING id''', (jid, str(self.settings.group_id), self.settings.group_id))).fetchone()
            if row:
                await c.execute("INSERT INTO audit_log(actor_id,action,details) VALUES(%s,'retry_job',%s)", (user['id'], Jsonb({'job_id': str(jid)})))
            await self.reply(c, job, 'Задача поставлена на повтор.' if row else 'Подходящая завершившаяся ошибкой задача не найдена. Повторять старые входящие ответы этой командой нельзя.')
        elif command == '/application':
            try:
                aid = str(uuid.UUID(parts[1]))
            except (IndexError, ValueError):
                await self.reply(c, job, 'Формат: /application UUID_заявки')
                return
            rows = await self.rows(c)
            row = next((r for r in rows if r['application_id'] == aid), None)
            if not row:
                await self.reply(c, job, 'Заявка этого набора не найдена.')
                return
            text = f"{row['candidate'] or 'Без имени'}\nID: {aid}\nБалл: {row['score'] if row['score'] is not None else 'Ожидает оценки'}\nНаправления: {', '.join(row['directions'])}\n\n{row['summary'] or ''}\n\n{row['answers'] or ''}"
            if row['interview_questions']:
                text += '\n\nВопросы собеседования:\n' + '\n'.join(row['interview_questions'])
            if row['files']:
                text += '\n\nДокументы:\n' + row['files']
            await self.reply(c, job, text)
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
            await self.reply(c, job, 'Доступно: /top /application ID /export /stats /score /notify /jobs /retry ID')

    async def rows(self, c, campaign=None):
        return await (await c.execute('''SELECT a.id::text application_id,u.name candidate,u.vk_id,
            a.status,a.selected_directions directions,e.score::float8 score,
            CASE WHEN e.source='human' AND m.id IS NOT NULL THEN m.summary ELSE e.summary END summary,
            COALESCE(m.criteria_results,e.criteria_results) criteria_results,
            COALESCE(NULLIF(e.interview_questions,'[]'::jsonb),m.interview_questions,'[]'::jsonb) interview_questions,
            CASE WHEN cardinality(e.recommended_directions)>0 THEN e.recommended_directions ELSE m.recommended_directions END recommended_directions,
            e.source,CASE WHEN e.source='human' THEN e.summary END manual_reason,
            (SELECT string_agg(CASE WHEN f.storage_key LIKE 'vk:%%' THEN 'https://vk.com/' || substr(f.storage_key,4) ELSE f.storage_key END,E'\n')
             FROM files f WHERE f.application_id=a.id AND f.kind='resume') files,
            (SELECT string_agg(an.question_text || E'\n' || an.answer_text,E'\n\n' ORDER BY an.revision)
             FROM answers an WHERE an.application_id=a.id) answers
            FROM applications a JOIN users u ON u.id=a.user_id
            LEFT JOIN LATERAL (SELECT * FROM evaluations ev WHERE ev.application_id=a.id AND ev.answer_revision=a.revision AND ev.source='model'
                ORDER BY ev.created_at DESC,ev.id DESC LIMIT 1) m ON true
            LEFT JOIN LATERAL (SELECT * FROM evaluations ev WHERE ev.application_id=a.id AND ev.answer_revision=a.revision
                ORDER BY (ev.source='human') DESC,ev.created_at DESC,ev.id DESC LIMIT 1) e ON true
            WHERE a.group_id=%s AND a.campaign=%s ORDER BY e.score DESC NULLS LAST,a.submitted_at,a.id''',
            (self.settings.group_id, campaign or self.settings.campaign))).fetchall()

