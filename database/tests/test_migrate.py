from pathlib import Path
import pytest
from gim_db.migrate import migrate


def test_missing_migration_directory_fails_closed(tmp_path):
    # A packaged installation must not report success after applying zero files.
    with pytest.raises(FileNotFoundError):migrate('not-a-database-dsn',tmp_path/'missing')
