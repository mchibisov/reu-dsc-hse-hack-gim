"""Русский UTF-8 и BOM должны работать независимо от кодировки Windows."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from test_shared_service import FakeRepository, MemoryService


class RubricEncodingTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_message_pins_utf8_bom_rubric_without_changing_russian(self):
        rubric = {'approved_by': 'Тестовая команда', 'scoring_rule': 'Мотивация и опыт',
                  'criteria': [{'code': 'motivation', 'name': 'Мотивация', 'max_points': 3}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rubric.json'
            path.write_text(json.dumps({'version': 'test', 'rubric': rubric}, ensure_ascii=False),
                            encoding='utf-8-sig')
            repo = FakeRepository([])
            repo.pin_rubric = AsyncMock()
            settings = SimpleNamespace(group_id=17, recruitment_id=uuid4(),
                                       analysis_rubric_path=str(path))
            service = MemoryService(repo, settings)
            service._advance = AsyncMock()
            event = {'id': uuid4(), 'payload': {'group_id': 17, 'event': {
                'group_id': 17, 'type': 'message_new', 'event_id': 'encoding-test',
                'object': {'message': {'from_id': 42, 'peer_id': 42, 'text': '/start'}}}}}
            await service.incoming(event)
            repo.pin_rubric.assert_awaited_once_with(repo.app['id'], rubric, 'test')
            service._advance.assert_awaited_once()
