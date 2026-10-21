import pytest

from gim_bot.storage import Store


@pytest.fixture
async def store(tmp_path):
    db = Store(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.initialize()
    yield db
    await db.close()
