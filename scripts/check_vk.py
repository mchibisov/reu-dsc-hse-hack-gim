"""Read-only проверка сообщества и Long Poll; токен/LP key не сохраняются."""
import asyncio
import json
from pathlib import Path

import httpx
from dotenv import dotenv_values


async def main():
    project = Path(__file__).resolve().parents[1]
    config = dotenv_values(project / '.env')
    token = config.get('VK_TOKEN', '')
    group = config.get('VK_GROUP_ID', '')
    report = {'group_id': int(group), 'methods': {}}
    async with httpx.AsyncClient(timeout=20) as client:
        for method in ('groups.getById', 'groups.getLongPollSettings', 'groups.getLongPollServer'):
            response = await client.post('https://api.vk.com/method/' + method,
                data={'access_token': token, 'v': '5.199', 'group_id': group})
            entry = {'http_status': response.status_code}
            body = response.json()
            if 'error' in body:
                entry['error_code'] = body['error'].get('error_code')
                entry['error_msg'] = str(body['error'].get('error_msg', '')).replace(token, '[REDACTED]')[:300]
            else:
                data = body.get('response', {})
                if method == 'groups.getById':
                    groups = data.get('groups', []) if isinstance(data, dict) else data
                    entry['matches_group'] = any(g.get('id') == int(group) for g in groups)
                elif method == 'groups.getLongPollSettings':
                    entry.update(enabled=data.get('is_enabled'), api_version=data.get('api_version'),
                                 message_new=data.get('events', {}).get('message_new'))
                else:
                    entry['server_key_present'] = bool(data.get('server') and data.get('key') and data.get('ts'))
            report['methods'][method] = entry
    output = project.parent/'results/2026-10-21-bootstrap-gim-vk-live-01/artifacts/access.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
