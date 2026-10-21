"""Настройки private runtime. Пароли и токены исключены из repr и ошибок."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from psycopg.conninfo import conninfo_to_dict


@dataclass(frozen=True)
class SharedSettings:
    database_bot_url: str = field(repr=False)
    database_worker_url: str = field(repr=False)
    database_staff_url: str = field(repr=False)
    vk_token: str = field(repr=False)
    group_id: int
    recruitment_id: UUID
    storage_dir: str
    consent_version: str = 'gim-v1'
    max_followups: int = 3
    max_answer_length: int = 2000
    concurrency: int = 4
    api_version: str = '5.199'
    llm_base_url: str = 'https://polza.ai/api/v1'
    llm_api_key: str = field(default='',repr=False)
    llm_model: str = 'deepseek/deepseek-v4.1-flash-1017'
    excel_access_code: str = field(default='',repr=False)

    @classmethod
    def load(cls):
        required = ('DATABASE_BOT_URL', 'DATABASE_WORKER_URL', 'DATABASE_STAFF_URL',
                    'VK_GROUP_ID', 'RECRUITMENT_ID')
        missing = [name for name in required if not os.environ.get(name, '').strip()]
        if missing:
            raise ValueError('Заполните .env: ' + ', '.join(missing))
        urls = [os.environ[name].strip() for name in required[:3]]
        for name, dsn in zip(required[:3], urls):
            try:
                params = conninfo_to_dict(dsn)
            except Exception:
                raise ValueError(f'{name}: неверная строка подключения') from None
            user = params.get('user', '').split('.')[0]
            if user in {'postgres', 'gim_test', 'supabase_admin'} or not user:
                raise ValueError(f'{name}: нужен отдельный runtime login, не оператор БД')
        try:
            group = int(os.environ['VK_GROUP_ID'])
            recruitment = UUID(os.environ['RECRUITMENT_ID'])
            concurrency = int(os.environ.get('WORKER_CONCURRENCY', '4'))
            followups = int(os.environ.get('MAX_FOLLOWUPS', '3'))
            answer_length = int(os.environ.get('MAX_ANSWER_LENGTH', '2000'))
        except (ValueError, TypeError):
            raise ValueError('Проверьте VK_GROUP_ID, RECRUITMENT_ID и числовые настройки') from None
        if group <= 0 or not 1 <= concurrency <= 8 or not 0 <= followups <= 3 or not 100 <= answer_length <= 20000:
            raise ValueError('VK_GROUP_ID > 0; WORKER_CONCURRENCY 1–8; MAX_FOLLOWUPS 0–3; MAX_ANSWER_LENGTH 100–20000')
        consent = os.environ.get('CONSENT_VERSION', 'gim-v1').strip()
        if not consent:
            raise ValueError('CONSENT_VERSION не должен быть пустым')
        return cls(*urls, os.environ.get('VK_TOKEN', ''), group, recruitment,
                   os.environ.get('STORAGE_DIR', str(Path('runtime/files').resolve())),
                   consent, followups, answer_length, concurrency,
                   os.environ.get('VK_API_VERSION', '5.199'),
                   os.environ.get('LLM_BASE_URL','https://polza.ai/api/v1'),
                   os.environ.get('LLM_API_KEY',''),
                   os.environ.get('LLM_MODEL','deepseek/deepseek-v4.1-flash-1017'),
                   os.environ.get('EXCEL_ACCESS_CODE',''))
