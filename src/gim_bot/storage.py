import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import Settings
from .models import Application, Base, ExportRequest, MessageEvent, RuntimeState, now
from .questionnaire import QUESTIONS, applicable, select_followups, validate_answer

CONFIRMATION = 'Спасибо! Ваша анкета получена. Сотрудники музея рассмотрят её и свяжутся с вами.'


@dataclass
class Reply:
    text: str
    completed: bool = False
    application_id: int | None = None
    personalize: bool = False


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
                event = await session.scalar(select(MessageEvent).where(
                    MessageEvent.user_id == user_id, MessageEvent.event_id == str(event_id)))
                if event:
                    return Reply(**event.result)
                app = await session.scalar(select(Application).where(
                    Application.user_id == user_id).with_for_update())
                reply = await self._handle(session, app, user_id, text.strip())
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
                await session.delete(app)
                await session.execute(delete(MessageEvent).where(MessageEvent.user_id == user_id))
                return Reply('Ваша анкета и ответы удалены.')
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

    async def replace_followups(self, user_id, questions: list[dict], event_id):
        async with self._locks.setdefault(user_id, asyncio.Lock()):
            async with self.transaction() as session:
                app = await session.scalar(select(Application).where(Application.user_id == user_id))
                if not app or app.status != 'followups' or app.followup_cursor:
                    return None
                if questions:
                    app.followups = [{**q, 'answer': '', 'source': 'llm'} for q in questions]
                reply = Reply(self._prompt(app), application_id=app.id)
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
