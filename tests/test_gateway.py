import httpx
import pytest

from gim_bot.gateway import app


@pytest.fixture
def gateway(monkeypatch):
    from gim_bot.config import Settings
    monkeypatch.setattr('gim_bot.gateway.get_settings', lambda: Settings(internal_api_key='internal-test-key'))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


async def test_gateway_auth_blocks_read_or_generation(gateway):
    async with gateway:
        response = await gateway.post('/analyze', json={'answers': {'motivation': 'test'}})
        assert response.status_code == 403


async def test_gateway_rejects_oversized_answer(gateway):
    async with gateway:
        response = await gateway.post('/analyze', headers={'X-Internal-Key': 'internal-test-key'},
                                      json={'answers': {'motivation': 'x' * 20001}})
        assert response.status_code == 422
