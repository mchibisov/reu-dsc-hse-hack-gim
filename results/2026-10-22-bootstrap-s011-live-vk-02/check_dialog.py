"""Целевой VK ID задаётся аргументом, в отчёт не попадает."""
import asyncio
import json
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from gim.config import load_dotenv
from gim.vk import VK,VKAPIError


async def main():
    load_dotenv(ROOT/'.env')
    vk=VK(SimpleNamespace(vk_token=os.environ['VK_TOKEN'],group_id=int(os.environ['VK_GROUP_ID']),api_version='5.199'))
    result={}
    try:
        response=await vk.call('messages.getHistory',group_id=vk.settings.group_id,peer_id=int(sys.argv[1]),count=40)
        records=sorted(response.get('items',[]),key=lambda m:(m.get('date',0),m.get('conversation_message_id',m.get('id',0))))
        result['message_count_read']=len(records)
        result['recent_metadata']=[]
        for message in records[-12:]:
            text=message.get('text','')
            entry={'direction':'bot' if message.get('out') else 'user','age_seconds':max(0,int(time.time())-message.get('date',0))}
            if not message.get('out'):
                entry['is_start']=text.strip().casefold() in {'начать','старт','/start','начать анкету'}
                entry['is_status']=text.strip().casefold() in {'статус','/status'}
            else:
                match=re.search(r'Основная анкета\s*·\s*(\d+)\s+из\s+(\d+)',text)
                if match:entry['progress']={'question':int(match[1]),'total':int(match[2])}
                entry['completed']='Анкета получена' in text
                entry['welcome']='Я бот волонтёрской программы' in text or 'я бот волонтёрской программы' in text
                entry['status_reply']='Статус анкеты:' in text
                entry['text_length']=len(text)
            result['recent_metadata'].append(entry)
        starts=[]
        for position,message in enumerate(records):
            if not message.get('out') and message.get('text','').strip().casefold() in {'начать','старт','/start','начать анкету'}:
                following=next((m for m in records[position+1:] if m.get('out')),None)
                starts.append({'start_age_seconds':max(0,int(time.time())-message.get('date',0)),
                    'reply_found':following is not None,'reply_delay_seconds':following['date']-message['date'] if following else None})
        result['start_checks']=starts[-3:]
    except VKAPIError as exc:
        result={'error_code':exc.code}
    except Exception as exc:
        result={'error_type':type(exc).__name__}
    finally:
        await vk.close()
    data=json.dumps(result,ensure_ascii=True,indent=2)
    (Path(__file__).parent/'dialog-result.json').write_text(data,encoding='utf-8')
    print(data)


if __name__=='__main__':asyncio.run(main())
