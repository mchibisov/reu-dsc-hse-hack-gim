"""Живой smoke только на вымышленной анкете, без контактов и реальных данных."""
import asyncio
import json
import logging
import time
from pathlib import Path

from gim_bot.analysis import Provider
from gim_bot.config import get_settings
from gim_bot.questionnaire import select_followups

ANSWERS = {
    'status': 'работаю', 'university': 'Окончил исторический факультет', 'course': 'окончил',
    'interests': 'История Москвы и музейные коллекции',
    'experience': 'Был фотографом на трёх музейных мероприятиях. Сам снимал на камеру, отбирал и обрабатывал фотографии в Lightroom.',
    'languages': 'Английский B2', 'motivation': 'Хочу помогать Историческому музею рассказывать об истории через фотографии.',
    'expectations': 'Хочу участвовать в создании материалов о коллекциях и событиях музея.',
    'hours': '8 часов в месяц, могу приезжать в музей в Москве по выходным',
    'hobbies': 'Фотография архитектуры', 'directions': 'медиа', 'source': 'сайт музея',
}


async def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('httpx').setLevel(logging.CRITICAL)
    settings = get_settings()
    provider = Provider(settings)
    started = time.perf_counter()
    try:
        analysis = await provider.analyze(ANSWERS)
        analysis_time = round(time.perf_counter() - started, 3)
        started_followups = time.perf_counter()
        followups = await provider.followups(ANSWERS, select_followups(ANSWERS))
        report = {'model': settings.llm_model, 'data': 'synthetic only',
            'analysis_available': analysis is not None, 'score': analysis.get('score') if analysis else None,
            'criterion_count': len(analysis['criteria']) if analysis else 0,
            'analysis_seconds': analysis_time, 'followups_available': followups is not None,
            'followup_seconds': round(time.perf_counter() - started_followups, 3),
            'followups': followups or [], 'request_key_not_logged': True}
        output = Path('../results/2026-10-21-bootstrap-gim-mistral-03/artifacts/smoke.json')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
    finally:
        await provider.close()


if __name__ == '__main__':
    asyncio.run(main())
