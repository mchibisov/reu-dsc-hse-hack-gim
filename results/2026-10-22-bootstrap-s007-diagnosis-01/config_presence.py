"""Только имена настроенных параметров и несекретные group/model/host."""
import json
from pathlib import Path
from urllib.parse import urlparse

rows = []
for path in (Path('../gim_shared/.env'), Path('../gim_bot/.env')):
    if not path.exists():
        continue
    values = dict(line.split('=', 1) for line in path.read_text(encoding='utf-8-sig').splitlines()
                  if '=' in line and not line.startswith('#'))
    rows.append({'file': str(path), 'configured_keys': [key for key, value in values.items() if value.strip()],
                 'group': values.get('VK_GROUP_ID'), 'model': values.get('LLM_MODEL'),
                 'db_host': urlparse(values.get('DATABASE_BOT_URL', '')).hostname})
print(json.dumps(rows, ensure_ascii=False))
