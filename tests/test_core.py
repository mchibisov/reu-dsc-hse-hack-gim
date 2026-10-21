import io
import unittest
import zipfile
from xml.etree import ElementTree as ET

from gim.dialog import transition
from gim.xlsx import export_xlsx


class DialogTests(unittest.TestCase):
    def test_no_data_before_consent(self):
        state, code, reply, done = transition({}, 'Старт')
        self.assertEqual(state['step'], 'consent')
        state, code, reply, done = transition(state, 'нет')
        self.assertIsNone(code)
        self.assertFalse(done)
        self.assertEqual(state['step'], 'consent')

    def test_blank_answer_does_not_advance(self):
        state, *_ = transition({}, 'Старт')
        state, *_ = transition(state, 'Согласен')
        after, code, _, done = transition(state, '  ')
        self.assertEqual(after, state)
        self.assertIsNone(code)
        self.assertFalse(done)

    def test_complete_funds_application(self):
        state, *_ = transition({}, 'Старт')
        state, *_ = transition(state, 'Согласен')
        codes = []
        for text in ['Иван', 'История', 'Работал в архиве', 'Английский B1',
                     'фонды', 'Хочу помогать музею', '5 часов в неделю',
                     'Читаю', 'Аккуратность', 'VK', 'Готов к каталогизации', 'Медиа']:
            state, code, reply, done = transition(state, text)
            if code:
                codes.append(code)
        self.assertTrue(done)
        self.assertEqual(state['directions'], ['funds'])
        self.assertIn('followup_funds', codes)
        self.assertNotIn('followup_media', codes)
        again, code, _, done = transition(state, 'Старт')
        self.assertEqual(again, state)
        self.assertIsNone(code)
        self.assertFalse(done)

    def test_invalid_direction_keeps_question(self):
        state = {'step': 'directions', 'directions': []}
        after, code, _, _ = transition(state, 'что-нибудь')
        self.assertEqual(after, state)
        self.assertIsNone(code)


class ExcelTests(unittest.TestCase):
    def test_long_summary_is_not_lost(self):
        data = export_xlsx([{'application_id': 'a', 'summary': 'А' * 40000 + 'УНИКАЛЬНЫЙ_КОНЕЦ'}])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read('xl/worksheets/sheet1.xml').decode()
        self.assertTrue('УНИКАЛЬНЫЙ_КОНЕЦ' in xml)

    def test_untrusted_text_is_literal_and_xml_valid(self):
        data = export_xlsx([{'candidate': '=HYPERLINK("bad")', 'summary': 'Музей <ГИМ> & фонд', 'score': 0}])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if name.endswith('.xml'):
                    ET.fromstring(z.read(name))
            xml = z.read('xl/worksheets/sheet1.xml').decode()
        self.assertNotIn('<f>', xml)
        self.assertIn('HYPERLINK', xml)
        self.assertIn('Музей', xml)


if __name__ == '__main__':
    unittest.main()
