import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path='.env'):
    """Load a local dotenv file; deployment variables always take precedence."""
    file = Path(path)
    if not file.exists():
        return
    for line in file.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or not key.strip().replace('_', '').isalnum():
            raise ValueError('Invalid dotenv assignment')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value.replace('\\n', '\n'))


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
    test_mode: bool = False
    followup_url: str = ''
    service_token: str = ''
    job_kinds: tuple[str, ...] = ()

    @classmethod
    def load(cls):
        result = cls(
            os.environ['DATABASE_URL'], os.environ.get('VK_TOKEN', ''),
            int(os.environ.get('VK_GROUP_ID') or '0'), os.environ.get('CAMPAIGN', 'autumn-2026'),
            tuple(int(v.strip()) for v in os.environ.get('ADMIN_VK_IDS', '').split(',') if v.strip()),
            os.environ.get('CONSENT_TEXT', ''), os.environ.get('SCORING_URL', ''),
            os.environ.get('SCORING_TOKEN', ''), os.environ.get('STORAGE_DIR', '/data/files'),
            int(os.environ.get('WORKER_CONCURRENCY', '4')), os.environ.get('VK_API_VERSION', '5.199'),
            os.environ.get('TEST_MODE', '').lower() in ('true', '1'),
            os.environ.get('FOLLOWUP_URL', ''), os.environ.get('SERVICE_TOKEN', ''),
            tuple(v.strip() for v in os.environ.get('JOB_KINDS', '').split(',') if v.strip()),
        )
        if not 1 <= result.concurrency <= 8:
            raise ValueError('WORKER_CONCURRENCY must be between 1 and 8')
        if result.group_id < 0 or not result.campaign.strip():
            raise ValueError('Invalid group or campaign')
        if result.test_mode and not result.admin_ids:
            raise ValueError('TEST_MODE requires ADMIN_VK_IDS')
        if set(result.job_kinds) - {'dialog', 'send', 'send_file', 'score', 'export', 'prepare_followups'}:
            raise ValueError('Unknown JOB_KINDS entry')
        return result
