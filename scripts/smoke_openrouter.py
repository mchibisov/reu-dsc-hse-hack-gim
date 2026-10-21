"""Два ограниченных запроса на вымышленной анкете; основной режим не меняется."""
import asyncio
import json
import logging
import time
from pathlib import Path

from dotenv import dotenv_values
from smoke_mistral import ANSWERS

from gim_bot.analysis import Provider
from gim_bot.config import Settings
from gim_bot.questionnaire import select_followups


async def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('httpx').setLevel(logging.CRITICAL)
    project = Path(__file__).resolve().parents[1]
    secret = dotenv_values(project / '.env').get('OPENROUTER_API_KEY', '')
    settings = Settings(llm_api_key=secret, llm_model='openai/gpt-4.1-mini',
                        llm_base_url='https://openrouter.ai/api/v1',
                        llm_timeout=30, followup_timeout=10)
    provider = Provider(settings)
    responses = []

    async def record(response):
        entry = {'status': response.status_code}
        if response.is_error:
            await response.aread()
            entry['error'] = response.text.replace(secret, '[REDACTED]')[:500]
        responses.append(entry)

    provider.client.event_hooks['response'] = [record]
    started = time.perf_counter()
    try:
        result = await provider.analyze(ANSWERS)
        analysis_seconds = round(time.perf_counter() - started, 3)
        started = time.perf_counter()
        questions = await provider.followups(ANSWERS, select_followups(ANSWERS))
        report = {'data': 'synthetic only', 'model': settings.llm_model,
                  'analysis_validated': result is not None,
                  'criterion_count': len(result['criteria']) if result else 0,
                  'analysis_seconds': analysis_seconds, 'analysis_timeout': settings.llm_timeout,
                  'followups_validated': questions is not None,
                  'followup_count': len(questions or []),
                  'followup_seconds': round(time.perf_counter() - started, 3),
                  'followup_timeout': settings.followup_timeout,
                  'responses': responses, 'default_llm_still_disabled': True}
        output = project.parent/'results/2026-10-21-bootstrap-gim-openrouter-02/artifacts/smoke.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
    finally:
        await provider.close()


if __name__ == '__main__':
    asyncio.run(main())
