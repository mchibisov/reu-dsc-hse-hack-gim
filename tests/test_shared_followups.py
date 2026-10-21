import unittest

from gim.shared_domain import select_followups


class LibraryFollowups(unittest.TestCase):
    def template(self, slot, text, directions=None):
        return dict(id=slot, kind='followup', target_slot=slot, text=text,
                    directions=directions or [], position=1)

    def test_relevant_museum_question_does_not_require_prior_experience(self):
        templates=[self.template('media_activity','Какая деятельность внутри направления вас привлекает?', ['media']),
                   self.template('collections_interest','Какие фонды вас привлекают для работы?', ['collections'])]
        found=select_followups(templates,[],['media'],3,{'experience':{'answer_text':'Нет опыта'}})
        self.assertEqual([t['target_slot'] for t in found],['media_activity'])

    def test_already_answered_topic_not_asked_again(self):
        t=self.template('teamwork','Вам интереснее работать в команде или индивидуально вести проект?')
        self.assertEqual(select_followups([t],[{'source':'generated','target_slot':'teamwork'}],[],3),[])

    def test_no_speculative_exams_or_limit_overflow(self):
        t=self.template('exam','Представьте ситуацию: как вы поступите?')
        self.assertEqual(select_followups([t],[],['media'],3),[])
        self.assertEqual(select_followups([self.template('teamwork','В команде или индивидуально?')],[],[],0),[])

    def test_library_does_not_repeat_explicit_preferences_and_schedule(self):
        ts=[self.template('media_activity','Какая деятельность вас привлекает?', ['media']),
            self.template('schedule','Предпочитаете регулярный график или гибкий?'),
            self.template('other_commitments','В настоящее время вы состоите в других волонтёрских программах?')]
        answers={'expectations':{'answer_text':'Интересуют посты и фото'},
                 'available_time':{'answer_text':'По субботам, других волонтёрских программ нет'}}
        self.assertEqual(select_followups(ts,[],['media'],3,answers),[])
