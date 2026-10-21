import os,unittest
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock
from gim.serverless import callback_allowed,receive
class CallbackTests(unittest.IsolatedAsyncioTestCase):
 async def test_unauthenticated_requests_never_open_database(self):
  with patch.dict(os.environ,{'VK_CALLBACK_SECRET':'test-secret'}),patch('gim.serverless.create_pool') as connect:
   settings=SimpleNamespace(group_id=17)
   self.assertEqual(await receive({'type':'message_new','group_id':17,'secret':'bad'},settings),(403,'forbidden'))
   self.assertFalse(callback_allowed({'group_id':18,'secret':'test-secret'},settings))
   connect.assert_not_called()
 async def test_confirmation_is_authenticated_and_does_not_connect(self):
  with patch.dict(os.environ,{'VK_CALLBACK_SECRET':'test-secret','VK_CONFIRMATION':'confirmation'}),patch('gim.serverless.create_pool') as connect:
   self.assertEqual(await receive({'type':'confirmation','group_id':17,'secret':'test-secret'},SimpleNamespace(group_id=17)),(200,'confirmation'))
   connect.assert_not_called()
