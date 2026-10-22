"""Реальные API с локальным секретом, только обезличенный результат."""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from gim.config import load_dotenv
from gim.vk import VK, VKAPIError


async def main():
    load_dotenv(ROOT/'.env')
    settings=SimpleNamespace(vk_token=os.environ['VK_TOKEN'],group_id=int(os.environ['VK_GROUP_ID']),
                             api_version=os.environ.get('VK_API_VERSION','5.199'))
    vk=VK(settings)
    result={'runtime_missing':[name for name in ('RECRUITMENT_ID','DATABASE_BOT_URL','DATABASE_WORKER_URL',
             'DATABASE_STAFF_URL','LLM_API_KEY') if not os.environ.get(name,'').strip()]}
    try:
        try:
            permissions=await vk.call('groups.getTokenPermissions')
            result['token_valid']=True
            result['permissions']=[p['name'] for p in permissions.get('permissions',[])]
        except VKAPIError as exc:
            result['token_valid']=False
            result['token_error_type']=type(exc).__name__
            result['token_error_code']=exc.code
            return result
        checks=[
            ('community','groups.getById',{'group_ids':settings.group_id}),
            ('callback','groups.getCallbackServers',{'group_id':settings.group_id}),
            ('longpoll','groups.getLongPollSettings',{'group_id':settings.group_id}),
            ('messages','messages.getConversations',{'count':5,'group_id':settings.group_id}),
        ]
        for name,method,params in checks:
            try:
                response=await vk.call(method,**params)
                if name=='community':
                    groups=response.get('groups',[]) if isinstance(response,dict) else response
                    result[name]={'target_found':any(g.get('id')==settings.group_id for g in groups)}
                elif name=='callback':
                    items=response.get('items',[])
                    result[name]={'count':len(items),'servers':[{'status':item.get('status'),
                        'expected_host':urlparse(item.get('url','')).hostname=='gim-volunteer-bot.vercel.app'} for item in items]}
                elif name=='longpoll':
                    result[name]={'enabled':bool(response.get('is_enabled')),
                                  'message_new':bool(response.get('events',{}).get('message_new'))}
                else:
                    result[name]={'api_readable':True,'conversation_count':response.get('count')}
            except VKAPIError as exc:
                result[name]={'error_code':exc.code,'error_type':type(exc).__name__}
            except Exception as exc:
                result[name]={'error_type':type(exc).__name__}
        return result
    finally:
        await vk.close()


if __name__=='__main__':
    try:
        result=asyncio.run(main())
    except Exception as exc:
        result={'error_type':type(exc).__name__}
    encoded=json.dumps(result,ensure_ascii=True,indent=2)
    (Path(__file__).parent/'live-result.json').write_text(encoded,encoding='utf-8')
    print(encoded)
