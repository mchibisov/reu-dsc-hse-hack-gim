from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = Field(default='sqlite+aiosqlite:///gim.db', repr=False)
    vk_token: str = Field(default='', repr=False)
    vk_group_id: int = 0
    vk_api_version: str = '5.199'
    admin_ids: str = ''
    excel_access_code: str = Field(default='', repr=False)
    internal_api_key: str = Field(default='', repr=False)
    gateway_url: str = ''
    llm_api_key: str = Field(default='', repr=False)
    llm_base_url: str = 'https://openrouter.ai/api/v1'
    llm_model: str = ''
    llm_fallback_model: str = ''
    llm_reasoning_enabled: bool | None = None
    llm_max_tokens: int = Field(default=1800, ge=256, le=8192)
    llm_timeout: float = 12
    followup_timeout: float = 3
    llm_concurrency: int = Field(default=4, ge=1, le=32)
    max_followups: int = Field(default=3, ge=0, le=4)
    max_answer_length: int = Field(default=2000, ge=100, le=10000)
    consent_text: str = 'Согласны на обработку анкеты по политике https://shm.ru/politika-konfidentsialnosti/?'
    consent_version: str = 'museum-policy-2026-10-21'
    worker_max_jobs: int = Field(default=5, ge=1, le=20)
    worker_poll_interval: float = Field(default=1, ge=0.1, le=30)
    bot_concurrency: int = Field(default=20, ge=1, le=100)

    @property
    def admins(self) -> frozenset[int]:
        return frozenset(int(x.strip()) for x in self.admin_ids.split(',') if x.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
