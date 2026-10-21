"""Groq smoke with synthetic data; never log API keys, error bodies or real answers."""
import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

from gim_bot.analysis import Provider
from gim_bot.config import Settings

BASE_URL = 'https://api.groq.com/openai/v1'
SYNTHETIC = {
    'status': 'Работаю, могу приходить по субботам.',
    'experience': 'В прошлом году снимал музейные мероприятия, сам отбирал и обрабатывал фотографии.',
    'motivation': 'Хочу помогать Историческому музею делать доступные материалы об истории.',
    'expectations': 'Хочу получить опыт музейной фотографии и работы в команде.',
    'hours': 'Могу выделять восемь часов в месяц по субботам.',
    'hobbies': 'Фотография и история.', 'directions': 'медиа',
}


async def probe(model, provider_probe=False, *, base_url=BASE_URL,
                key_variable='GROQ_API_KEY', provider_name='Groq'):
    project = Path(__file__).resolve().parents[1]
    key = dotenv_values(project / '.env').get(key_variable, '')
    result = {'provider': provider_name, 'model': model, 'scope': 'synthetic only'}
    if not key:
        return {**result, 'error': 'missing_local_key'}
    async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
        headers = {'Authorization': 'Bearer ' + key}
        try:
            response = await client.get(base_url + '/models', headers=headers)
            result['models_http_status'] = response.status_code
            if not response.is_success:
                return result
            result['model_available'] = model in {x['id'] for x in response.json().get('data', [])}
            if not result['model_available']:
                result['related_models'] = [x['id'] for x in response.json().get('data', [])
                                            if 'deepseek' in x.get('id', '').lower()][:30]
                return result
            started = time.monotonic()
            payload = {
                'model': model, 'temperature': 0, 'max_tokens': 512,
                'messages': [{'role': 'user', 'content': 'Return a JSON object with ok set to true.'}],
                'response_format': {'type': 'json_schema', 'json_schema': {'name': 'smoke', 'strict': True,
                    'schema': {'type': 'object', 'additionalProperties': False,
                               'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']}}},
            }
            if provider_name == 'Groq':
                payload['reasoning_effort'] = 'low'
            elif provider_name == 'Polza':
                payload['reasoning'] = {'enabled': False}
            response = await client.post(base_url + '/chat/completions', headers=headers, json=payload)
            result.update(generation_http_status=response.status_code,
                          generation_duration_ms=round((time.monotonic() - started) * 1000))
            body = response.json()
            if response.is_success:
                result['structured_json_valid'] = json.loads(body['choices'][0]['message']['content']) == {'ok': True}
                result['total_tokens'] = body.get('usage', {}).get('total_tokens')
            else:
                error = body.get('error', {})
                result['error_code'] = error.get('code')
                result['error_type'] = error.get('type')
                return result
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as error:
            result['error_type'] = type(error).__name__
            return result
    if provider_probe:
        settings = Settings(_env_file=None, llm_api_key=key, llm_model=model, llm_base_url=base_url,
                            llm_timeout=30, followup_timeout=8, gateway_url='', internal_api_key='',
                            llm_reasoning_enabled=False if provider_name == 'Polza' else None,
                            llm_max_tokens=4096)
        provider = Provider(settings)
        response_metadata = []

        async def record_metadata(response):
            await response.aread()
            entry = {'http_status': response.status_code}
            try:
                body = response.json()
                choices = body.get('choices', [])
                if choices:
                    content = choices[0].get('message', {}).get('content')
                    entry.update(finish_reason=choices[0].get('finish_reason'),
                                 content_length=len(content) if isinstance(content, str) else 0,
                                 content_type=type(content).__name__)
                else:
                    error = body.get('error', {})
                    if isinstance(error, dict):
                        entry.update(error_code=error.get('code'), error_type=error.get('type'))
                entry['usage'] = body.get('usage')
            except (ValueError, TypeError, AttributeError):
                entry['json_body_valid'] = False
            response_metadata.append(entry)

        provider.client.event_hooks['response'] = [record_metadata]
        try:
            started = time.monotonic()
            analysis = await provider.analyze(SYNTHETIC)
            result.update(provider_analysis_valid=analysis is not None,
                          provider_analysis_duration_ms=round((time.monotonic() - started) * 1000),
                          criteria_count=len(analysis['criteria']) if analysis else 0,
                          synthetic_score=analysis['score'] if analysis else None)
            started = time.monotonic()
            questions = await provider.followups(SYNTHETIC, [
                {'question': 'Какие работы вы выполняли лично?', 'field': 'experience', 'topic': 'media'}])
            result.update(provider_followups_valid=questions is not None,
                          provider_followups_duration_ms=round((time.monotonic() - started) * 1000),
                          followup_count=len(questions or []))
            result['provider_response_metadata'] = response_metadata
        finally:
            await provider.close()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='openai/gpt-oss-120b')
    parser.add_argument('--provider', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(probe(args.model, args.provider))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    if not report.get('structured_json_valid') or (args.provider and not (
        report.get('provider_analysis_valid') and report.get('provider_followups_valid')
    )):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
