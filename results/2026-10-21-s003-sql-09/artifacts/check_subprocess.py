"""No network; compare Windows child import with minimal inherited OS variables."""
import os
import subprocess
import sys

for label, names in [('path_only', ('PATH',)),
                     ('windows_runtime', ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP'))]:
    env = {name: os.environ[name] for name in names if name in os.environ}
    result = subprocess.run([sys.executable, '-c', 'import psycopg; print("imported")'],
                            env=env, capture_output=True)
    print(label, 'exit:', result.returncode)
    print('stdout:', ascii(result.stdout))
    print('stderr:', ascii(result.stderr))
