import unittest
from types import SimpleNamespace
from uuid import uuid4

from test_shared_service import FakeRepository, MemoryService, template


class RetiredQuestionTests(unittest.IsolatedAsyncioTestCase):
    async def test_late_reply_to_skipped_question_is_not_assigned_to_next_field(self):
        repo=FakeRepository([template('consent',1),template('faculty',2)])
        old=dict(id=uuid4(),source='base',status='skipped',target_slot='university_other',
                 template_id=uuid4(),position=8,text='ВУЗ (Другое)',request_key='old')
        repo.questions.append(old)
        service=MemoryService(repo,SimpleNamespace(group_id=17,recruitment_id=uuid4(),
            consent_version='test',max_followups=0,max_answer_length=2000))
        event=dict(id=uuid4(),payload={'group_id':17,'receipt':{
            'app_id':str(repo.app['id']),'question_id':str(old['id'])},'event':{
            'type':'message_new','group_id':17,'event_id':str(uuid4()),
            'object':{'message':{'from_id':42,'peer_id':42,'text':'Запоздавший ответ'}}}})
        await service.incoming(event)
        self.assertEqual(repo.answers,[])
        self.assertEqual(repo.questions[-1]['target_slot'],'consent')
