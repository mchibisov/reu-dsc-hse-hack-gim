"""Проверка ключа и модели; секрет и данные аккаунта не выводятся."""
import asyncio
import json
from pathlib import Path

import httpx
from dotenv import dotenv_values


async def main():
    project = Path(__file__).resolve().parents[1]
    key = dotenv_values(project / '.env').get('OPENROUTER_API_KEY', '')
    async with httpx.AsyncClient(timeout=20) as client:
        auth = await client.get('https://openrouter.ai/api/v1/key',
                                headers={'Authorization': f'Bearer {key}'})
        models = await client.get('https://openrouter.ai/api/v1/models')
    selected = next((m for m in models.json().get('data', [])
                     if m['id'] == 'openai/gpt-4.1-mini'), None) if models.status_code == 200 else None
    report = {'auth_status': auth.status_code, 'models_status': models.status_code,
              'selected_model': selected['id'] if selected else None,
              'supported_parameters': selected.get('supported_parameters', []) if selected else [],
              'pricing': selected.get('pricing', {}) if selected else {}}
    output = project.parent / 'results/2026-10-21-bootstrap-gim-openrouter-01/artifacts/access.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
