"""Read-only подтверждения; тексты, имена и peer IDs не сохраняются."""
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from gim.config import load_dotenv
from gim.vk import VK, VKAPIError


async def main():
    load_dotenv(ROOT/'.env')
    settings=SimpleNamespace(vk_token=os.environ['VK_TOKEN'],group_id=int(os.environ['VK_GROUP_ID']),api_version='5.199')
    vk=VK(settings)
    report={}
    try:
        servers=await vk.call('groups.getCallbackServers',group_id=settings.group_id)
        for server in servers.get('items',[]):
            if server.get('status')=='ok':
                config=await vk.call('groups.getCallbackSettings',group_id=settings.group_id,server_id=server['id'])
                report['callback_message_new']=bool(config.get('events',{}).get('message_new'))
                report['callback_api_version']=config.get('api_version')
        conversations=await vk.call('messages.getConversations',group_id=settings.group_id,count=5)
        reports=[]
        for item in conversations.get('items',[]):
            peer=item['conversation']['peer']['id']
            if item['conversation']['peer']['type']!='user':continue
            history=await vk.call('messages.getHistory',peer_id=peer,group_id=settings.group_id,count=20)
            records=sorted(history.get('items',[]),key=lambda m:(m.get('date',0),m.get('conversation_message_id',m.get('id',0))))
            outgoing=[m for m in records if m.get('out')]
            incoming=[m for m in records if not m.get('out')]
            recent=outgoing[-1] if outgoing else None
            progress=[]
            for message in outgoing:
                match=re.search(r'Основная анкета\s*·\s*(\d+)\s+из\s+(\d+)',message.get('text',''))
                if match:progress.append({'question':int(match[1]),'total':int(match[2])})
            observed=[]
            for pos,message in enumerate(records):
                if not message.get('out') and message.get('text','').strip().casefold() in {'начать','/start','старт'}:
                    following=next((m for m in records[pos+1:] if m.get('out')),None)
                    if following:observed.append(max(0,following['date']-message['date']))
            reports.append({'outgoing_in_recent_history':len(outgoing),'incoming_in_recent_history':len(incoming),
                'latest_outgoing_age_seconds':int(time.time())-recent['date'] if recent else None,
                'observed_progress':progress[-3:], 'start_to_next_outgoing_seconds':observed[-2:]})
        report['recent_conversations']=reports
    except VKAPIError as exc:
        report['error_code']=exc.code
    except Exception as exc:
        report['error_type']=type(exc).__name__
    finally:
        await vk.close()
    encoded=json.dumps(report,ensure_ascii=True,indent=2)
    (Path(__file__).parent/'recent-result.json').write_text(encoded,encoding='utf-8')
    print(encoded)


if __name__=='__main__':asyncio.run(main())
