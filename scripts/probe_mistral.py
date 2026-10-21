"""Диагностика HTTP отказа, без ключа и без реальных пользовательских данных."""
import asyncio
import json
from pathlib import Path

from smoke_mistral import ANSWERS

from gim_bot.analysis import Provider
from gim_bot.config import get_settings


async def main():
    cfg = get_settings()
    observations = []

    async def observe(response):
        await response.aread()
        item = {'status': response.status_code}
        if not response.is_success:
            item['error'] = response.text.replace(cfg.llm_api_key, '[REDACTED]')[:1500]
        observations.append(item)

    provider = Provider(cfg)
    provider.client.event_hooks['response'] = [observe]
    try:
        result = await provider.analyze(ANSWERS)
        report = {'analysis_available': result is not None, 'http': observations}
        path = Path('../results/2026-10-21-bootstrap-gim-mistral-04/artifacts/diagnostic.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
    finally:
        await provider.close()


if __name__ == '__main__':
    asyncio.run(main())
