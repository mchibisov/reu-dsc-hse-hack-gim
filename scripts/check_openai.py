"""Один read-only запрос OpenAI; ключ и текст ошибки не записываются."""
import asyncio
import json
from pathlib import Path

import httpx
from dotenv import dotenv_values


async def main():
    project = Path(__file__).resolve().parents[1]
    key = dotenv_values(project / '.env').get('OPENAI_CANDIDATE_KEY', '')
    report = {'endpoint': 'https://api.openai.com/v1/models', 'generation_requested': False}
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.get(report['endpoint'], headers={'Authorization': f'Bearer {key}'})
        report['http_status'] = response.status_code
        try:
            body = response.json()
        except ValueError:
            body = {}
        error = body.get('error', {})
        if isinstance(error, dict):
            report['error_code'] = error.get('code')
            report['error_type'] = error.get('type')
        if response.is_success:
            report['model_count'] = len(body.get('data', []))
    except httpx.HTTPError as error:
        report['network_error_type'] = type(error).__name__
    output = project.parent/'results/2026-10-21-bootstrap-gim-openai-01/artifacts/access.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
