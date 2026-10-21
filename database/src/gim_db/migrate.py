"""Apply checksummed migrations with an operator connection, never a runtime login."""
import hashlib
import os
from pathlib import Path
import psycopg


def migrate(dsn: str, directory: Path | None = None) -> None:
    directory = directory or Path(os.environ.get('MIGRATIONS_DIR', 'supabase/migrations'))
    paths = sorted(directory.glob('*.sql'))
    if not paths:
        raise FileNotFoundError(f'No SQL migrations in {directory}')
    with psycopg.connect(dsn, autocommit=True) as c:
        # Shared lock across deployers; one transaction per migration.
        c.execute('SELECT pg_advisory_lock(20853041)')
        try:
            c.execute('CREATE SCHEMA IF NOT EXISTS gim_meta')
            c.execute('REVOKE ALL ON SCHEMA gim_meta FROM PUBLIC')
            c.execute('CREATE TABLE IF NOT EXISTS gim_meta.migrations(name text PRIMARY KEY, sha256 text NOT NULL)')
            for path in paths:
                sql = path.read_text(encoding='utf-8')
                digest = hashlib.sha256(sql.encode()).hexdigest()
                row = c.execute('SELECT sha256 FROM gim_meta.migrations WHERE name=%s', (path.name,)).fetchone()
                if row:
                    if row[0] != digest:
                        raise ValueError(f'Migration checksum changed: {path.name}')
                    continue
                with c.transaction():
                    c.execute(sql, prepare=False)
                    c.execute('INSERT INTO gim_meta.migrations VALUES(%s,%s)', (path.name, digest))
        finally:
            c.execute('SELECT pg_advisory_unlock(20853041)')


if __name__ == '__main__':
    migrate(os.environ['DATABASE_ADMIN_URL'])
