import os
from dataclasses import dataclass


@dataclass
class Settings:
    database_url: str
    vk_token: str
    group_id: int
    campaign: str
    admin_ids: tuple[int, ...]
    consent_text: str
    scoring_url: str
    scoring_token: str
    storage_dir: str
    concurrency: int
    api_version: str

    @classmethod
    def load(cls):
        return cls(
            os.environ['DATABASE_URL'], os.environ.get('VK_TOKEN', ''),
            int(os.environ.get('VK_GROUP_ID') or '0'), os.environ.get('CAMPAIGN', 'autumn-2026'),
            tuple(int(v.strip()) for v in os.environ.get('ADMIN_VK_IDS', '').split(',') if v.strip()),
            os.environ.get('CONSENT_TEXT', ''), os.environ.get('SCORING_URL', ''),
            os.environ.get('SCORING_TOKEN', ''), os.environ.get('STORAGE_DIR', '/data/files'),
            int(os.environ.get('WORKER_CONCURRENCY', '4')), os.environ.get('VK_API_VERSION', '5.199'),
        )
