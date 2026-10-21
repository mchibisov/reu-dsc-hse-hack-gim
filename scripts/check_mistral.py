"""Проверка доступа; выводит только HTTP-статус и названия моделей, без секрета."""
import asyncio
import json
from pathlib import Path

import httpx

from gim_bot.config import get_settings


async def main():
    cfg = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            response = await client.get(cfg.llm_base_url.rstrip('/') + '/models',
                headers={'Authorization': f'Bearer {cfg.llm_api_key}'})
            result = {'http_status': response.status_code, 'key_configured': bool(cfg.llm_api_key)}
            if response.is_success:
                result['models'] = [m['id'] for m in response.json().get('data', [])
                                    if 'small' in m.get('id', '') and m.get('capabilities', {}).get('completion_chat')]
        except httpx.HTTPError as error:
            result = {'network_error': type(error).__name__}
    output = Path('../results/2026-10-21-bootstrap-gim-mistral-01/artifacts/access.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    asyncio.run(main())
