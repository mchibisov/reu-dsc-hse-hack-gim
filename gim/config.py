import os
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
