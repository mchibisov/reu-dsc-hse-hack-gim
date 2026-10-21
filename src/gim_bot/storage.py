import asyncio
import hashlib
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import timedelta
from time import time
from uuid import uuid4

from sqlalchemy import String, and_, cast, delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import Settings
from .export_access import (
    CodeExportAttempt,
    CodeExportLimit,
    CodeExportPermit,
    code_fingerprint,
    code_matches,
)
from .models import (
    Application,
    BackgroundJob,
    Base,
    DeletedEvent,
    ExportRequest,
    MessageEvent,
    OutgoingReply,
    RuntimeState,
    now,
)
from .questionnaire import QUESTIONS, applicable, select_followups, validate_answer

CONFIRMATION = 'Спасибо! Ваша анкета получена. Сотрудники музея рассмотрят её и свяжутся с вами.'
DELETED = 'Ваша анкета и ответы удалены.'


def event_digest(user_id, event_id):
    return hashlib.sha256(f'{user_id}:{event_id}'.encode()).hexdigest()


@dataclass
class Reply:
    text: str
    completed: bool = False
    application_id: int | None = None
    personalize: bool = False
    deleted: bool = False
    ignored: bool = False


class Store:
    def __init__(self, database_url: str, settings: Settings | None = None):
        self.database_url = database_url
        self.settings = settings or Settings(database_url=database_url)
        options = {'connect_args': {'timeout': 30}} if database_url.startswith('sqlite') else {}
        self.engine = create_async_engine(database_url, pool_pre_ping=True, hide_parameters=True, **options)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self._locks: dict[int, asyncio.Lock] = {}
        self._sqlite_writer = asyncio.Lock() if database_url.startswith('sqlite') else None

    @asynccontextmanager
    async def transaction(self):
        # SQLite допускает одного писателя; PostgreSQL продолжает писать конкурентно.
        if self._sqlite_writer:
            async with self._sqlite_writer, self.sessions.begin() as session:
                yield session
        else:
            async with self.sessions.begin() as session:
                yield session

    async def initialize(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self):
        await self.engine.dispose()

    async def get_by_user(self, user_id):
        async with self.sessions() as session:
            return await session.scalar(select(Application).where(Application.user_id == user_id))

    async def get(self, application_id):
        async with self.sessions() as session:
            return await session.get(Application, application_id)

    async def current_key(self, user_id):
        app = await self.get_by_user(user_id)
        return QUESTIONS[app.cursor].key if app and app.status == 'base' else 'followup'

    async def list_applications(self, completed_only=True):
        async with self.sessions() as session:
            stmt = select(Application)
            if completed_only:
                stmt = stmt.where(Application.status == 'completed')
            stmt = stmt.order_by(Application.score.desc().nullslast(), Application.id)
            return list(await session.scalars(stmt))

    async def handle_message(self, user_id: int, event_id: str, text: str) -> Reply:
        async with self._locks.setdefault(user_id, asyncio.Lock()):
            async with self.transaction() as session:
                tombstone = await session.get(DeletedEvent, event_digest(user_id, event_id))
                if tombstone:
                    return Reply(DELETED, deleted=True) if tombstone.confirmation else Reply('', ignored=True)
                event = await session.scalar(select(MessageEvent).where(
                    MessageEvent.user_id == user_id, MessageEvent.event_id == str(event_id)))
                if event:
                    return Reply(**event.result)
                app = await session.scalar(select(Application).where(
                    Application.user_id == user_id).with_for_update())
                reply = await self._handle(session, app, user_id, text.strip())
                if reply.deleted:
                    session.add(DeletedEvent(digest=event_digest(user_id, event_id), confirmation=True))
                else:
                    session.add(MessageEvent(user_id=user_id, event_id=str(event_id), result=asdict(reply)))
                return reply

    async def _handle(self, session, app, user_id, text):
        command = text.lower()
        if command == '/delete':
            if app:
                app.delete_pending = True
                return Reply('Для удаления анкеты и всех ответов напишите УДАЛИТЬ. Любой другой ответ отменит удаление.')
            return Reply('Сохранённой анкеты нет.')
        if app and app.delete_pending:
            app.delete_pending = False
            if command == 'удалить':
                prior_events = list(await session.scalars(select(MessageEvent).where(MessageEvent.user_id == user_id)))
                for prior in prior_events:
                    session.add(DeletedEvent(digest=event_digest(user_id, prior.event_id), confirmation=False))
                await session.delete(app)
                await session.execute(delete(MessageEvent).where(MessageEvent.user_id == user_id))
                await session.execute(delete(OutgoingReply).where(OutgoingReply.user_id == user_id))
                return Reply(DELETED, deleted=True)
            return Reply('Удаление отменено. Напишите /start, чтобы продолжить.')
        if not app:
            if command in ('согласен', 'согласна', 'даю согласие'):
                app = Application(user_id=user_id, consent_version=self.settings.consent_version,
                                  answers={}, followups=[], cursor=0, status='base')
                session.add(app)
                await session.flush()
                return Reply(QUESTIONS[0].text, application_id=app.id)
            return Reply('Волонтёрская программа ГИМ. Опрос займёт ориентировочно 5–7 минут. '
                         + self.settings.consent_text + '\nДля начала напишите «Согласен» или «Согласна».')
        if app.status == 'completed':
            return Reply(CONFIRMATION, application_id=app.id)
        if command in ('/start', 'старт', '/status', '/help'):
            return Reply(self._prompt(app), application_id=app.id)
        if command.startswith('/'):
            return Reply('Доступны /start, /status, /delete.\n' + self._prompt(app), application_id=app.id)
        key = QUESTIONS[app.cursor].key if app.status == 'base' else 'followup'
        error = validate_answer(key, text, self.settings.max_answer_length)
        if error:
            return Reply(error, application_id=app.id)
        if app.status == 'base':
            app.answers = {**app.answers, key: text}
            app.cursor += 1
            while app.cursor < len(QUESTIONS) and not applicable(QUESTIONS[app.cursor].key, app.answers):
                app.answers = {**app.answers, QUESTIONS[app.cursor].key: 'не относится'}
                app.cursor += 1
            if app.cursor == len(QUESTIONS):
                app.followups = select_followups(app.answers, self.settings.max_followups)
                app.status = 'followups'
                app.followup_cursor = 0
                if app.followups:
                    return Reply(self._prompt(app), application_id=app.id, personalize=True)
                return self._complete(app)
        else:
            followups = [dict(q) for q in app.followups]
            followups[app.followup_cursor]['answer'] = text
            app.followups = followups
            app.followup_cursor += 1
            if app.followup_cursor == len(app.followups):
                return self._complete(app)
        return Reply(self._prompt(app), application_id=app.id)

    @staticmethod
    def _prompt(app):
        if app.status == 'base':
            return QUESTIONS[app.cursor].text
        return app.followups[app.followup_cursor]['question']

    @staticmethod
    def _complete(app):
        app.status = 'completed'
        app.completed_at = now()
        app.analysis_status = 'queued'
        return Reply(CONFIRMATION, completed=True, application_id=app.id)

    async def replace_followups(self, user_id, questions: list[dict], event_id, prefix=''):
        async with self._locks.setdefault(user_id, asyncio.Lock()):
            async with self.transaction() as session:
                app = await session.scalar(select(Application).where(Application.user_id == user_id))
                if not app or app.status != 'followups' or app.followup_cursor:
                    return None
                if questions:
                    app.followups = [{**q, 'answer': '', 'source': 'llm'} for q in questions]
                prompt = (prefix + '\n\n' if prefix else '') + self._prompt(app)
                reply = Reply(prompt, application_id=app.id)
                event = await session.scalar(select(MessageEvent).where(
                    MessageEvent.user_id == user_id, MessageEvent.event_id == str(event_id)))
                if event:
                    event.result = asdict(reply)
                return reply

    async def claim_analysis(self, application_id):
        async with self.transaction() as session:
            result = await session.execute(update(Application).where(
                Application.id == application_id, Application.status == 'completed',
                Application.analysis_status == 'queued').values(analysis_status='processing'))
            return result.rowcount == 1

    async def requeue_analysis(self, application_id):
        """Только явный операторский повтор отсутствующей аналитики, без изменения ответов."""
        async with self.transaction() as session:
            changed = await session.execute(update(Application).where(
                Application.id == application_id, Application.status == 'completed',
                Application.analysis_status == 'no_analytics',
                or_(Application.analysis.is_(None), cast(Application.analysis, String) == 'null')
            ).values(analysis_status='queued'))
            if changed.rowcount != 1:
                return False
            session.add(BackgroundJob(key=f'reanalysis:{application_id}:{uuid4().hex}',
                                      kind='analyze_application', payload={'args': [application_id]}))
            return True

    async def save_analysis(self, application_id, analysis, score, rubric_version):
        async with self.transaction() as session:
            await session.execute(update(Application).where(
                Application.id == application_id, Application.analysis_status == 'processing').values(
                analysis=analysis, score=score, rubric_version=rubric_version,
                analysis_status='ready' if analysis else 'no_analytics'))

    async def mark_notified(self, application_id, admin_id):
        async with self.transaction() as session:
            app = await session.scalar(select(Application).where(Application.id == application_id).with_for_update())
            if app and admin_id not in app.notified_admins:
                app.notified_admins = [*app.notified_admins, admin_id]

    async def request_export(self, admin_id, request_key):
        async with self.transaction() as session:
            request = await session.scalar(select(ExportRequest).where(ExportRequest.request_key == request_key))
            if not request:
                request = ExportRequest(admin_id=admin_id, request_key=request_key)
                session.add(request)
                await session.flush()
            return request.id

    async def request_code_export(self, user_id: int, event_id: str, provided: str) -> Reply:
        """Атомарно учитывать попытку/дубликат и выдавать разрешение только на этот запрос."""
        digest = event_digest(user_id, 'code-export:' + event_id)
        instant = time()
        insert = pg_insert if self.engine.dialect.name == 'postgresql' else sqlite_insert
        async with self.transaction() as session:
            # INSERT первым получает SQLite write lock; FOR UPDATE сериализует PostgreSQL.
            await session.execute(insert(CodeExportLimit).values(
                user_id=user_id, failures=[]
            ).on_conflict_do_nothing(index_elements=['user_id']))
            limit = await session.get(CodeExportLimit, user_id, with_for_update=True)
            previous = await session.get(CodeExportAttempt, digest)
            if previous:
                return self._code_export_reply(previous.request_id)
            failures = [timestamp for timestamp in limit.failures if timestamp > instant - 600]
            limit.failures = failures
            request_id = None
            if len(failures) < 5 and code_matches(provided, self.settings.excel_access_code):
                request = ExportRequest(admin_id=user_id, request_key='code:' + digest)
                session.add(request)
                await session.flush()
                request_id = request.id
                session.add(CodeExportPermit(request_id=request_id, user_id=user_id,
                    fingerprint=code_fingerprint(self.settings.excel_access_code)))
            elif len(failures) < 5:
                limit.failures = [*failures, instant]
            session.add(CodeExportAttempt(digest=digest, request_id=request_id))
            return self._code_export_reply(request_id)

    @staticmethod
    def _code_export_reply(request_id):
        if request_id is not None:
            return Reply(f'Выгрузка №{request_id} поставлена в очередь. Файл придёт в этот диалог.')
        return Reply('Запрос недоступен. Проверьте данные или повторите позже.')

    async def authorize_export(self, request_id: int, user_id: int, settings: Settings) -> bool:
        async with self.transaction() as session:
            request = await session.get(ExportRequest, request_id)
            if not request or request.admin_id != user_id or request.status != 'queued':
                return False
            if request.request_key.startswith('code:'):
                permit = await session.get(CodeExportPermit, request_id)
                allowed = bool(permit and permit.user_id == user_id and settings.excel_access_code
                    and code_matches(permit.fingerprint, code_fingerprint(settings.excel_access_code)))
                if not allowed:
                    request.status = 'revoked'
                return allowed
            return user_id in settings.admins

    async def pending_exports(self):
        async with self.sessions() as session:
            return list(await session.scalars(select(ExportRequest).where(ExportRequest.status == 'queued')))

    async def export_done(self, request_id):
        async with self.transaction() as session:
            await session.execute(update(ExportRequest).where(ExportRequest.id == request_id).values(status='sent'))

    async def recover_stale(self):
        async with self.transaction() as session:
            await session.execute(update(Application).where(
                Application.analysis_status == 'processing', Application.updated_at < now() - timedelta(minutes=10)
            ).values(analysis_status='queued'))
            stale = (OutgoingReply.status == 'sending', OutgoingReply.updated_at < now() - timedelta(minutes=10))
            await session.execute(update(OutgoingReply).where(*stale, OutgoingReply.attempts >= 5).values(
                status='failed', user_id=None, text=''))
            await session.execute(update(OutgoingReply).where(*stale, OutgoingReply.attempts < 5).values(status='queued'))

    async def queue_reply(self, user_id, text, event_id):
        key = event_digest(user_id, 'outgoing:' + event_id)
        async with self.transaction() as session:
            if not await session.get(OutgoingReply, key):
                await session.execute(update(OutgoingReply).where(
                    OutgoingReply.user_id == user_id, OutgoingReply.status.in_(('queued', 'sending'))
                ).values(status='superseded', user_id=None, text=''))
                session.add(OutgoingReply(key=key, user_id=user_id, text=text))
        return key

    async def pending_replies(self, due_only=False):
        async with self.sessions() as session:
            statement = select(OutgoingReply).where(OutgoingReply.status == 'queued')
            if due_only:
                statement = statement.where(OutgoingReply.next_attempt <= now())
            return list(await session.scalars(statement))

    async def claim_reply(self, key):
        async with self.transaction() as session:
            result = await session.execute(update(OutgoingReply).where(
                OutgoingReply.key == key, OutgoingReply.status == 'queued', OutgoingReply.attempts < 5,
                OutgoingReply.next_attempt <= now()).values(status='sending', attempts=OutgoingReply.attempts + 1))
            return result.rowcount == 1

    async def get_reply(self, key):
        async with self.sessions() as session:
            return await session.get(OutgoingReply, key)

    async def finish_reply(self, key, success):
        async with self.transaction() as session:
            reply = await session.get(OutgoingReply, key, with_for_update=True)
            if not reply or reply.status != 'sending':
                return
            if success or reply.attempts >= 5:
                reply.status = 'sent' if success else 'failed'
                reply.text, reply.user_id = '', None
            else:
                reply.status = 'queued'
                reply.next_attempt = now() + timedelta(seconds=min(60 * reply.attempts, 300))

    async def load_runtime(self, key):
        async with self.sessions() as session:
            value = await session.get(RuntimeState, key)
            return value.value if value else None

    async def save_runtime(self, key, value):
        async with self.transaction() as session:
            saved = await session.get(RuntimeState, key)
            if saved:
                saved.value = value
            else:
                session.add(RuntimeState(key=key, value=value))

    async def enqueue_job(self, key: str, kind: str, args: list):
        insert = pg_insert if self.engine.dialect.name == 'postgresql' else sqlite_insert
        async with self.transaction() as session:
            await session.execute(insert(BackgroundJob).values(
                key=key, kind=kind, payload={'args': args}
            ).on_conflict_do_nothing(index_elements=['key']))

    async def claim_job(self):
        instant = now()
        expired = and_(BackgroundJob.status == 'running', BackgroundJob.lease_until <= instant)
        eligible = and_(BackgroundJob.attempts < 3, or_(
            and_(BackgroundJob.status == 'queued', BackgroundJob.next_attempt <= instant), expired))
        async with self.transaction() as session:
            await session.execute(update(BackgroundJob).where(expired, BackgroundJob.attempts >= 3).values(
                status='failed', payload={}, lease_token='', lease_until=None))
            key = await session.scalar(select(BackgroundJob.key).where(eligible).order_by(
                BackgroundJob.next_attempt, BackgroundJob.key).limit(1).with_for_update(skip_locked=True))
            if key is None:
                return None
            return await session.scalar(update(BackgroundJob).where(
                BackgroundJob.key == key, eligible).values(status='running', lease_token=uuid4().hex,
                    lease_until=instant + timedelta(minutes=10), attempts=BackgroundJob.attempts + 1
                ).returning(BackgroundJob))

    async def finish_job(self, key: str, token: str, success: bool, retry_delay: int | None = None):
        async with self.transaction() as session:
            job = await session.scalar(select(BackgroundJob).where(
                BackgroundJob.key == key, BackgroundJob.status == 'running',
                BackgroundJob.lease_token == token).with_for_update())
            if job is None:
                return False
            terminal = success or job.attempts >= 3
            result = await session.execute(update(BackgroundJob).where(
                BackgroundJob.key == key, BackgroundJob.status == 'running', BackgroundJob.lease_token == token
            ).values(status='done' if success else ('failed' if terminal else 'queued'),
                payload={} if terminal else job.payload, lease_token='', lease_until=None,
                next_attempt=now() + timedelta(seconds=60 * job.attempts if retry_delay is None else retry_delay)))
            return result.rowcount == 1
