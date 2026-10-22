"""OpenAI-compatible chat-completions client (Mistral/OpenRouter/custom provider)."""
import asyncio
import json
import logging
import time
import httpx


log=logging.getLogger(__name__)


class ModelUnavailable(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings):
        self.settings = settings

    async def complete(self, system, payload, *, reasoning_enabled=None):
        key = getattr(self.settings, 'llm_api_key', '')
        model = getattr(self.settings, 'llm_model', '')
        base = getattr(self.settings, 'llm_base_url', '')
        if not key or not model or not base:
            raise ModelUnavailable('Configure LLM_API_KEY, LLM_MODEL and LLM_BASE_URL')
        effort=getattr(self.settings,'llm_reasoning_effort','')
        enabled=getattr(self.settings,'llm_reasoning_enabled',False) if reasoning_enabled is None else reasoning_enabled
        reasoning={'reasoning':{'enabled':enabled}} if enabled is not None else ({'reasoning':{'effort':effort}} if effort else {})
        started=time.monotonic()
        try:
            async with asyncio.timeout(30), httpx.AsyncClient(timeout=httpx.Timeout(30,connect=3,pool=3)) as client:
                response = await client.post(base.rstrip('/') + '/chat/completions',
                    headers={'Authorization': 'Bearer ' + key}, json={
                        'model': model, 'temperature': 0.2, 'max_tokens': getattr(self.settings,'llm_max_tokens',6000),**reasoning,
                        'response_format': {'type': 'json_object'},
                        'messages': [{'role': 'system', 'content': system},
                                     {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]})
                if response.status_code != 200:
                    raise ModelUnavailable('Model HTTP status ' + str(response.status_code))
                result = response.json()
                usage=result.get('usage') or {}
                log.info('llm_response model=%s seconds=%.1f finish=%s input_tokens=%s output_tokens=%s cost_rub=%s',
                         model,time.monotonic()-started,result['choices'][0].get('finish_reason'),
                         usage.get('prompt_tokens'),usage.get('completion_tokens'),usage.get('cost_rub'))
                if result['choices'][0].get('finish_reason') in ('length', 'content_filter'):
                    raise ValueError('Incomplete model response')
                value = json.loads(result['choices'][0]['message']['content'])
                if not isinstance(value, dict):
                    raise ValueError('Expected JSON object')
                return value
        except ModelUnavailable:
            raise
        except (TimeoutError, httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
            # Never include provider bodies, candidate answers or credentials in errors.
            raise ModelUnavailable('Invalid or unavailable model response') from None
