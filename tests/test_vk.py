import unittest

from gim.vk import message_event, poll_next


class VKTests(unittest.TestCase):
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
