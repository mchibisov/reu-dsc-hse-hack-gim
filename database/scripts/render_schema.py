"""Render implemented tables from a live database; no personal records are read."""
import os
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import psycopg

out=Path(os.environ.get('SCHEMA_PNG','docs/database-schema.png'))
with psycopg.connect(os.environ['DATABASE_ADMIN_URL']) as c:
    metadata=c.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='gim' AND table_name IN (SELECT tablename FROM pg_tables WHERE schemaname='gim') ORDER BY table_name,ordinal_position").fetchall()
cols={}
for t,f in metadata:cols.setdefault(t,[]).append(f)
assert len(cols)==12
layout=[['users','recruitments','question_templates','staff_members'],['applications','dialog_questions','answers','evaluations'],['inbox_events','outbox_events','files','audit_log']]
selected={
 'users':['id','vk_id','full_name, email'],
 'recruitments':['id, group_id, status','questionnaire_version','rubric_version, rubric','direction_info, followup_policy'],
 'question_templates':['id, recruitment_id','code, kind, required','text, target_slot, directions','validation'],
 'staff_members':['id, user_id, group_id','role, active, revoked_at','notify_new_applications','added_by_staff_id'],
 'applications':['id, user_id, recruitment_id','status, answers_revision','current_question_id','birth_date, birth_date_answer_id','consent_version, consent_at','profile, selected_directions','decision, decision_by_staff_id'],
 'dialog_questions':['id, application_id, template_id','text, source, purpose, target_slot','based_on_revision, context','request_key, parent_question_id','position, status, asked_at'],
 'answers':['id, application_id, question_id','revision, answer_text, value','group_id, event_id','created_at'],
 'evaluations':['id, application_id, answers_revision','source, reviewer_staff_id, score','rubric_version, rubric_snapshot','criteria_results, input_snapshot','summary, interview_questions','request_key, source_event_id'],
 'inbox_events':['group_id + event_id (PK)','application_id, fingerprint','received_at'],
 'outbox_events':['id, application_id, file_id','recipient_staff_id, topic, payload','dedupe_key, vk_random_id','available_at, last_published_at','completed_at, publish_attempts','last_error_code'],
 'files':['id, recruitment_id, application_id','evaluation_id, requested_by_staff_id','kind, scope, status, version','answers_revision, ready_revision','storage_key, sha256, size_bytes','extracted_text, extraction_version','filters, snapshot_at'],
 'audit_log':['id, application_id','actor_staff_id, actor_user_id','action, details, created_at']}
notes={'users':'Общий человек, отдельно от полномочий','recruitments':'Правила и банк замораживаются при открытии','question_templates':'Банк отдельно от вопросов кандидату','staff_members':'Только своё сообщество и активное членство','applications':'Согласие, 18+, диалог; без лимита 100 заявок','dialog_questions':'Точный вопрос сохранён ДО отправки','answers':'Неизменяемая история; защита от дублей VK','evaluations':'Снимок + цитаты; ручная оценка приоритетна','inbox_events':'Ключ события и отпечаток содержимого','outbox_events':'Намерение в PostgreSQL; исполнитель ARQ','files':'Приватные объекты; XLSX набора без кандидата','audit_log':'Действия и ID; без текстов анкет и секретов'}
W,H=2880,1990; im=Image.new('RGB',(W,H),'#f1f5f9');d=ImageDraw.Draw(im)
font='/System/Library/Fonts/Supplemental/Arial.ttf'
f=lambda n:ImageFont.truetype(font,n)
d.text((60,40),'ГИМ · Реализованная БД для отбора волонтёров',font=f(54),fill='#10253f')
d.text((60,112),'12 таблиц в закрытой схеме gim · PostgreSQL + приватный Supabase Storage · 21.10.2026',font=f(27),fill='#455c72')
positions={}
for row,tables in enumerate(layout):
 for col,t in enumerate(tables):positions[t]=(60+col*710,245+row*525)
# Explicit key flow edges; auxiliary ownership is named on FK fields.
for a,b in [('users','applications'),('recruitments','question_templates'),('recruitments','applications'),('question_templates','dialog_questions'),('applications','dialog_questions'),('dialog_questions','answers'),('answers','evaluations'),('applications','inbox_events'),('dialog_questions','outbox_events'),('evaluations','files')]:
 x,y=positions[a];xx,yy=positions[b]
 if y==yy:
  pts=[(x+650,y+215),(xx,y+215)]
 else:
  pts=[(x+325,y+440),(x+325,y+480),(xx+325,y+480),(xx+325,yy)]
 d.line(pts,fill='#91a5b9',width=4)
 ex,ey=pts[-1];px,py=pts[-2]
 if ex>px:d.polygon([(ex,ey),(ex-14,ey-8),(ex-14,ey+8)],fill='#91a5b9')
 else:d.polygon([(ex,ey),(ex-8,ey-14),(ex+8,ey-14)],fill='#91a5b9')
for t,(x,y) in positions.items():
 d.rounded_rectangle((x,y,x+650,y+440),radius=20,fill='white',outline='#c9d5e1',width=2)
 d.rounded_rectangle((x,y,x+650,y+67),radius=20,fill='#12334f')
 d.rectangle((x,y+35,x+650,y+67),fill='#12334f')
 d.text((x+20,y+17),t,font=f(31),fill='white')
 for i,line in enumerate(selected[t]):d.text((x+20,y+88+i*34),line,font=f(23),fill='#19354f')
 d.text((x+20,y+395),notes[t],font=f(20),fill='#486b77')
d.text((60,1835),'Основная цепочка: анкета → сохранённый вопрос → версионный ответ → оценка с доказательствами.',font=f(29),fill='#10253f')
d.text((60,1885),'Стрелки показывают основной поток; служебные FK и ограничения — в миграциях. Данные таблиц не используются при рендере.',font=f(24),fill='#455c72')
out.parent.mkdir(parents=True,exist_ok=True);im.save(out)
print(out)
