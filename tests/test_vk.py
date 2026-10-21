import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from gim.vk import message_event, poll_next


class VKTests(unittest.TestCase):
    def test_event_without_event_id_uses_stable_message_identifier(self):
        event = {'type': 'message_new', 'group_id': 2,
                 'object': {'message': {'id': 77, 'conversation_message_id': 9, 'from_id': 10, 'peer_id': 10, 'text': 'Привет'}}}
        normalized = message_event(event)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized['event_id'], 'message:10:9')
    def test_only_private_incoming_messages_are_accepted(self):
        base = {'type': 'message_new', 'group_id': 2, 'event_id': 'abc',
                'object': {'message': {'from_id': 10, 'peer_id': 10, 'out': 0, 'text': 'Привет'}}}
        self.assertEqual(message_event(base)['object']['message']['text'], 'Привет')
        base['object']['message']['peer_id'] = 2000000001
        self.assertIsNone(message_event(base))

    def test_longpoll_lost_ts_and_expired_key(self):
        self.assertEqual(poll_next({'failed': 1, 'ts': '30'}, {'ts': '20'}), {'ts': '30'})
        self.assertIsNone(poll_next({'failed': 2}, {'ts': '20'}))
        self.assertIsNone(poll_next({'failed': 3}, {'ts': '20'}))
        self.assertEqual(poll_next({'ts': '21'}, {'ts': '20', 'key': 'k'}), {'ts': '21', 'key': 'k'})


class VKDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_candidate_has_navigation_and_personal_profile_buttons(self):
        import json
        from gim.vk import VK
        vk=VK(SimpleNamespace(vk_token='synthetic',api_version='5.199',group_id=17))
        vk.call=AsyncMock(return_value=123)
        try:
            await vk.send(42,'Профиль',99,question_slot='vk_url')
            keyboard=json.loads(vk.call.call_args.kwargs['keyboard'])
            actions=[b['action'] for row in keyboard['buttons'] for b in row]
            self.assertTrue({'Начать','Статус','Помощь','Использовать мою страницу'}<={a['label'] for a in actions})
            self.assertTrue(any(a.get('link')=='https://vk.com/id42' for a in actions))
        finally:await vk.close()

    async def test_error_code_is_safe_for_durable_logs(self):
        from gim.vk import VK
        vk=VK(SimpleNamespace(vk_token='private-token',api_version='5.199'))
        await vk.http.aclose()
        vk.http=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={
            'error':{'error_code':901,'error_msg':'private-token private answer','request_params':[{'value':'private-token'}]}})))
        try:
            with self.assertRaises(RuntimeError) as caught:
                await vk.call('messages.send')
            self.assertEqual(caught.exception.code,'vk_901')
            self.assertNotIn('private-token',str(caught.exception))
            self.assertNotIn('private answer',str(caught.exception))
        finally:await vk.close()

    async def test_disabled_keyboard_does_not_lose_message_or_file(self):
        from gim.vk import VK, VKAPIError
        vk=VK(SimpleNamespace(vk_token='synthetic',api_version='5.199',group_id=17))
        vk.call=AsyncMock(side_effect=[VKAPIError('messages.send',912),123])
        try:
            self.assertEqual(await vk.send(42,'Excel',99,attachment='doc_synthetic'),123)
            args=vk.call.call_args.kwargs
            self.assertNotIn('keyboard',args)
            self.assertEqual(args['random_id'],99)
            self.assertEqual(args['attachment'],'doc_synthetic')
        finally:await vk.close()
