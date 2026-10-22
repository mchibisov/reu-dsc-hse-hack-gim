"""Ограниченная по времени диагностика без токенов/конфигов аккаунтов."""
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
commands = {
    'wsl_status': ['wsl.exe', '--status'],
    'wsl_version': ['wsl.exe', '--version'],
    'docker_version': ['C:/Program Files/Docker/Docker/resources/bin/docker.exe', 'version'],
}
results = {}
for name, args in commands.items():
    try:
        run = subprocess.run(args, capture_output=True, timeout=30,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        def decode(data):
            return data.decode('utf-16-le' if b'\0' in data else 'utf-8', errors='replace')
        results[name] = {'exit_code': run.returncode, 'stdout': decode(run.stdout),
                         'stderr': decode(run.stderr)}
    except subprocess.TimeoutExpired:
        results[name] = {'state': 'timeout', 'timeout_seconds': 30}
(root / 'engine-before.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(results, ensure_ascii=False, indent=2))
