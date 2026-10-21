"""Явный операторский повтор анкет без аналитики. Без --apply только технические ID."""
import argparse
import asyncio
import json

from gim_bot.config import Settings
from gim_bot.storage import Store


async def run(apply=False):
    settings = Settings()
    if apply and not (settings.llm_api_key and settings.llm_model):
        raise SystemExit('Сначала настройте LLM в локальном .env')
    store = Store(settings.database_url, settings)
    try:
        apps = await store.list_applications()
        selected = [app.id for app in apps if app.analysis_status == 'no_analytics' and not app.analysis]
        queued = []
        if apply:
            for application_id in selected:
                if await store.requeue_analysis(application_id):
                    queued.append(application_id)
        print(json.dumps({'eligible_ids': selected, 'queued_ids': queued}))
    finally:
        await store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    asyncio.run(run(parser.parse_args().apply))
