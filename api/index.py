"""Vercel Python entry point. No personal data or secrets are returned."""
import asyncio,hmac,json,os,sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'database'/'src'))
from gim.shared_config import SharedSettings
from gim.serverless import receive,drain

class handler(BaseHTTPRequestHandler):
 server_version='GIM'
 sys_version=''
 def log_message(self,*args):pass # HTTP paths/headers may contain authentication material
 def reply(self,status,text,content='text/plain; charset=utf-8'):
  body=text.encode();self.send_response(status);self.send_header('Content-Type',content);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'");self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_GET(self):
  if self.path.split('?')[0]=='/health':return self.reply(200,'{"status":"ok","transport":"vk-callback"}','application/json')
  if self.path.split('?')[0]!='/':return self.reply(404,'not found')
  self.reply(200,'<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Волонтёры ГИМ</title><body style="font:20px system-ui;background:#faf7f3;color:#222;max-width:650px;margin:15vh auto;padding:24px"><p style="color:#a71930">ГОСУДАРСТВЕННЫЙ ИСТОРИЧЕСКИЙ МУЗЕЙ · ДЕМО</p><h1>Начните с желания помогать</h1><p>Пять направлений волонтёрства. Короткая анкета и персональные уточнения в VK. Решение о приглашении принимает сотрудник музея.</p><a style="display:inline-block;background:#a71930;color:white;padding:16px 24px;border-radius:12px;text-decoration:none" href="https://vk.me/club242476311">Открыть бота в VK →</a><p style="font-size:15px">Бот работает в личных сообщениях сообщества. Нажмите «Начать».</p></body></html>','text/html; charset=utf-8')
 def do_POST(self):
  try:
   path=self.path.split('?')[0]
   if path=='/work':
    key=os.environ.get('WORKER_DISPATCH_KEY','')
    if not key or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+key):return self.reply(403,'forbidden')
    return self.reply(200,asyncio.run(drain(SharedSettings.load())))
   if path!='/callback':return self.reply(404,'not found')
   length=int(self.headers.get('Content-Length','0'))
   if not 0<length<=131072:return self.reply(413,'invalid body size')
   event=json.loads(self.rfile.read(length))
   status,text=asyncio.run(receive(event,SharedSettings.load()));self.reply(status,text)
  except (ValueError,TypeError,json.JSONDecodeError):self.reply(400,'invalid request')
  except Exception as exc:
   print('request_failed error_type='+type(exc).__name__,flush=True)
   self.reply(503,'temporarily unavailable')
