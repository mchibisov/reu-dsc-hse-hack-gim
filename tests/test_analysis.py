import json

import httpx
import pytest

from gim_bot.analysis import AnalysisResult, Provider, sanitize_answers, validate_analysis
from gim_bot.config import Settings
from gim_bot.rubric import CRITERIA, score_evidence


def result(level=2):
    return {
        'criteria': [{'id': key, 'level': level, 'field': 'experience',
                      'quote': 'Снимал мероприятия', 'explanation': 'Указан конкретный опыт.'} for key in CRITERIA],
        'summary': 'Есть опыт фотографии.', 'recommended_direction': 'медиа',
        'rationale': 'Опыт фотографии.', 'interview_questions': ['Какие были задачи съёмки?'],
    }


@pytest.mark.parametrize('level,expected', [(0, 0), (1, 2), (2, 3)])
def test_score_boundaries(level, expected):
    assert score_evidence(AnalysisResult.model_validate(result(level)).criteria) == expected


def test_unknown_is_not_negative_and_insufficient_is_unscored():
    value = result()
    for item in value['criteria'][2:]:
        item.update(level=None, quote='', field='')
    assert score_evidence(AnalysisResult.model_validate(value).criteria) is None


def test_hallucinated_quote_is_rejected():
    with pytest.raises(ValueError, match='цитат'):
        validate_analysis(result(), {'experience': 'Опыт отсутствует'})


def test_unknown_or_duplicate_criteria_are_rejected():
    value = result()
    value['criteria'][-1]['id'] = value['criteria'][0]['id']
    with pytest.raises(ValueError):
        AnalysisResult.model_validate(value)


def test_privacy_and_future_outcomes_are_removed():
    answers = {'name': 'Иван Тестов', 'email': 'secret@example.org', 'birth_date': '01.01.2000',
               'experience': 'Я Иван Тестов, email secret@example.org, +7 (999) 123-45-67, vk.com/id123',
               'hours': '10', 'annual_hours': '100', 'accepted': 'да', 'retained': 'да', 'user_id': '123'}
    clean = sanitize_answers(answers)
    text = json.dumps(clean, ensure_ascii=False)
    assert set(clean) == {'experience', 'hours'}
    for pii in ('Иван', 'Тестов', 'secret@example.org', '999', 'vk.com/id123'):
        assert pii not in text


def test_sanitized_followup_answers_survive_gateway_boundary():
    answers = {'experience': 'Есть опыт', 'name': 'Иван Тестов'}
    safe = sanitize_answers(answers, [{'question': 'Что делали?', 'answer': 'Обрабатывал фотографии'}])
    assert sanitize_answers(safe)['followup_1_answer'] == 'Обрабатывал фотографии'


async def test_provider_disabled_and_failure_are_safe():
    def unexpected_request(request):
        pytest.fail('При отключённой модели внешних запросов быть не должно')

    provider = Provider(Settings(llm_api_key='', llm_model=''),
                        transport=httpx.MockTransport(unexpected_request))
    assert await provider.analyze({'experience': 'test'}) is None
    assert await provider.followups({'experience': 'test'}, []) is None
    await provider.close()
    calls = []

    def fail(request):
        calls.append(request)
        return httpx.Response(503)

    provider = Provider(Settings(llm_api_key='test', llm_model='test'),
                        transport=httpx.MockTransport(fail))
    assert await provider.analyze({'experience': 'test'}) is None
    assert len(calls) <= 2
    await provider.close()


async def test_valid_provider_result_has_server_calculated_score():
    def respond(request):
        payload = json.loads(request.content)
        assert payload['response_format']['type'] == 'json_schema'
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(result())}}]})
    provider = Provider(Settings(llm_api_key='test', llm_model='test'), transport=httpx.MockTransport(respond))
    analysis = await provider.analyze({'experience': 'Снимал мероприятия в музее'})
    assert analysis is not None
    assert analysis['score'] == 3
    assert analysis['rubric_version'] == 'gim-5-v1'
    await provider.close()
