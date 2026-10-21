# Контракт для Python-сервисов

## Граница доверия

`Repository` вызывается доверенными Python-сервисами, не браузером и не напрямую из произвольного VK payload. Бот проверяет callback secret/signature и community ID; кабинет проверяет серверную сессию/VK-подпись и получает из неё VK ID. Только этот **verified_vk_id** передаётся в staff-функции. Переданное пользователем `role`, `staff_id`, `group_id` или VK ID не удостоверяет личность.

- `gim_bot`: общие учётные данные, черновик анкеты, вопросы/ответы, inbox и намерения. Нет выдачи staff-прав, изменения правил, вставки оценок или решения о приёме.
- `gim_worker`: читает постоянные входы, записывает алгоритмическую оценку/файлы/результаты outbox. Не может вызвать функции ручной оценки и управления сотрудниками.
- `gim_staff`: нет SELECT таблиц; только ограниченные SQL-функции через Python-методы. Каждый вызов проверяет активность, сообщество и необходимую роль в текущей БД.
- Оператор: миграции, draft-конфигурация и bootstrap первого администратора. Его DSN не используется runtime.

Private SECURITY DEFINER-функции имеют фиксированный пустой search_path, отозванный PUBLIC EXECUTE, явно назначенных вызывающих. Supabase anon/authenticated не имеют прав на схему. Эти функции не выставлять как публичный RPC с входным actor_vk.

## Пулы и транзакции

```python
from gim_db.repository import Repository, create_pool
async with create_pool(BOT_DSN, max_size=5) as pool:
    bot = Repository(pool)
    application = await bot.start_application(recruitment_id, verified_vk_id)
```

Пулы создаются на процесс, не на запрос. Операции короткие; LLM/VK/парсинг файлов — вне открытой транзакции. Экспорт и контекст читаются согласованным REPEATABLE READ. Ошибки `Conflict`/SQLSTATE 23514/23505 означают перечитать состояние и показать подходящую ситуацию; не переадресовывать старый ответ на новый вопрос. При DB deadlock/serialization failure повторяется **вся** операция с тем же ключом, ограниченно и с jitter. Не логировать текст исключения драйвера, содержащий данные; логировать SQLSTATE, request/event UUID, topic и безопасный код.

## Сервис диалога

1. `start_application(recruitment_id, verified_vk_id)` → dict заявки. Идемпотентно по `(user,recruitment)`; набор должен быть активен.
2. Задать обязательные вопросы из банка. Для согласия сохранить raw answer и только после явного положительного подтверждения вызвать `set_consent(app_id, policy_version)`. При отказе не подавать заявку; прекращение и удаление ПДн согласовать с владельцем процесса.
3. После согласия `set_contacts(verified_vk_id, full_name=..., email=...)` хранит контакты общей учётной записи. Полные исходные ответы остаются в истории анкеты.
4. `dialog_context(app_id)` → application, questions, **вся история answers**, templates, known_facts, direction_info, followup_policy. Планировщик строит актуальные ответы по последней revision каждого question_id; учитывает уже заданные target_slot и purpose. Эти данные позволяют выбирать уместное уточнение; семантическое качество — обязанность планировщика.
5. `prepare_question(app_id, request_key=..., expected_revision=N, template_id=...)` копирует точный базовый вопрос; для уточнения передать `text`, `target_slot`, `purpose='clarify'/'expectations'`, `context` и при повторном уточнении `parent_question_id`. Для шаблонного уточнения можно передать template_id и персональный text.
6. Метод атомарно сохраняет вопрос и `question.send` в outbox **до отправки**. Повтор request_key возвращает сохранённую формулировку, даже если новая генерация отличается. Не отправлять сгенерированный текст в обход этого шага.
7. `record_answer(app_id, question_id, group_id=verified_group, event_id=vk_event_id, text=..., value=parsed_value, expected_revision=N)` → сохранённый answer. Тот же VK event c тем же содержимым вернёт прежний ответ; другое тело/заявка под тем же ключом отклоняется. Вопрос явно известен; не определять его по текущему состоянию после задержки события.
8. Для исправления передать **тот же** question_id, новый VK event ID и актуальную revision. Предыдущая запись не обновляется. Параллельный ответ со старой revision получает Conflict и остаётся неприменённым; вызывающий сервис повторно обрабатывает исходное событие после разрешения конфликта. Поданная заявка не редактируется и не возвращается в draft.
9. `set_profile(app_id, expected_revision=N, birth_date=date|None, selected_directions=[...], undecided=bool, facts={...}, birth_date_raw=..., birth_date_answer_id=...)`. Полную дату разобрать из конкретного ответа и сохранить ссылку; частичную историческую дату оставить raw. Факт имеет форму `{value:..., answer_ids:[...]}`. Не извлекать «известные» сведения из будущей активности/часов. Факты — вспомогательное состояние планировщика; оценщик получает исходные ответы.
10. `submit(app_id)` атомарно фиксирует подачу, `application.analyze` и уведомления подписанным активным сотрудникам своего сообщества. Проверяются согласие, возраст на московскую дату подачи, обязательный банк, направление/«не определился», отсутствие активного вопроса и незавершённого резюме. Повтор не создаёт задач заново. Подача через прямой SQL тоже использует эти ограничения и триггер outbox.

Отрицательный ответ и «не применимо» — содержательные ответы; пустой текст отклоняется. `validation` шаблона — правила для бота; DB не заменяет форматные проверки email/URL/даты. Для условного «ВУЗ (Другое)» сохранить явное «не применимо», а не молча опустить обязательный слот.

Коды направлений: `organizational`, `project`, `collections`, `inclusive`, `media`. `undecided=true` означает пустой selected_directions. «Совпали ли ожидания?» — вопросы `purpose='expectations'` с реальными задачами направления, готовностью к ним и альтернативам. Эти ответы попадают в «Ответы» и «Собеседование».

## Оценка LLM/baseline

`evaluation_snapshot(app_id, revision=None)` возвращает:

- `input_snapshot`: revision, **последние answer_ids** каждого вопроса на эту revision, IDs/sha256 последних готовых резюме;
- rubric и rubric_version из фиксированного набора;
- исходные тексты выбранных ответов и извлечённых резюме.

Резюме увеличивает общую ревизию входных данных при переходе в ready. Поэтому после него следующий ответ получает следующую revision, даже если между ответами был только файл.

LLM не создаёт критерии. Вызов `save_evaluation(app_id, snapshot=..., score=0..3, criteria=[...], summary=..., request_key=..., directions=[...], interview_questions=[...], model=..., prompt_version=..., source_event_id=...)` сохраняет новую неизменяемую запись. score — итог фиксированного scoring_rule, который должен применить сервис оценки; DB проверяет диапазон и структуру критериев, но не исполняет произвольную формулу из JSON.

```json
{
  "code": "CODE_FROM_APPROVED_RUBRIC",
  "points": 0.5,
  "reason": "Человеческое объяснение результата",
  "evidence": [
    {"source_type": "answer", "source_id": "ANSWER_UUID", "quote": "точная цитата"},
    {"source_type": "file", "source_id": "RESUME_UUID", "quote": "точная цитата из extracted_text", "page": 2}
  ]
}
```

Нужен ровно один результат для каждого кода rubric.criteria; points лежит в 0..max_points. Если доказательств нет, evidence=[] и needs_review=true. Источник из другого кандидата, устаревший заменённый ответ/резюме в новом снимке или несуществующая цитата отклоняются. Наличие подстроки проверяемо; правильность вывода из цитаты оценивает человек. Номер page — предоставленная парсером подсказка, его соответствие PDF-странице DB не проверяет.

Алгоритмическая запись и completed_at исходного `application.analyze` записываются **одной транзакцией**. Повторный request_key возвращает уже сохранённый результат. Не ставить completed_at до фиксации результата. Поздняя оценка алгоритма не перекрывает ручную оценку **той же** revision. Более свежая revision приоритетна; старая оценка обозначается evaluation_stale в выгрузке.

`curator_evaluation(verified_vk_id, app_id, revision=N, score=..., criteria=..., summary=..., request_key=...)` создаёт отдельную запись от активного сотрудника сообщества; исходная оценка алгоритма остаётся. Ручная правка требует текущую revision. `decide(verified_vk_id, app_id, 'invited'|'accepted'|'rejected')` — отдельное решение человека, не следствие балла.

## Фоновые задачи и ARQ

`python -m gim_db.outbox` — издатель. `arq gim_db.outbox.WorkerSettings` — исполнитель. Единственный брокер — Redis. Стабильный ARQ job ID: `gim:<outbox_uuid>`; Redis хранит только непрозрачный UUID, не анкету. В outbox есть available_at, last_published_at, publish_attempts, completed_at, last_error_code.

Команда предоставляет модуль `GIM_HANDLERS_MODULE`:

```python
HANDLERS = {
    'question.send': send_saved_question,
    'application.analyze': analyze_saved_snapshot,
    'staff.notify': notify_staff,
    'file.export': export_saved_bundle,
}
```

Каждый handler — `async def handler(event: dict)`. `question.send` получает event.question с точным text, vk_id, group_id; отправляет его через VK с event.vk_random_id. `application.analyze` получает event.snapshot и возвращает kwargs для save_evaluation: score, criteria, summary, directions, interview_questions, model, prompt_version. Не возвращать snapshot/request_key/source_event_id: worker подставляет их сам.

`staff.notify` перед отправкой использует `await send_staff_notification(repo,event,send_vk)` из gim_db.outbox. Хелпер повторно проверяет сотрудника непосредственно перед сетевым вызовом и передаёт `send_vk(vk_id,group_id,random_id)`. Длительную подготовку текста делать до хелпера. Ранее отправленное уведомление/HTTP-запрос в полёте не отзывается.

`file.export` получает event.payload.snapshot с уже зафиксированными четырьмя наборами данных. Не перечитывать текущие анкеты для этого файла. Получить pending file metadata по event.file_id, создать файл, загрузить immutable object, вызвать FileRepository.finish с фактическими SHA-256/размером; только потом handler возвращает успех. После падения повторять тот же file ID/object key. Постановку на экспорт делает staff через request_export, не произвольный клиент.

ARQ max_jobs=10, max_tries=5, timeout=180s, keep_result=0. При исчерпании повторов без business completion издатель снова опубликует событие; last_error_code/publish_attempts позволяют выявить застрявшую работу. LLM может вызываться повторно после потери Redis/процесса; фиксация оценки идемпотентна. Это at-least-once, не обещание exactly-once внешнего вызова.

## Excel/кабинет

`export_bundle(verified_vk_id,recruitment_id,application_id=None,filters={})` читает согласованный снимок. Поддержаны фильтры status, direction, decision. NULL score остаётся NULL; сортировка score DESC NULLS LAST, затем подача и UUID. Автор ручного изменения не смешивается с данными кандидата.

| Ключ | Назначение |
|---|---|
| Анкеты | Контакты, направления, стадия/решение, актуальная оценка, источник/автор, объяснение, revision и stale |
| Ответы | Полные формулировки всех вопросов и все версии ответов, value, is_latest, source/purpose/slot |
| Собеседование | Саммари, interview_questions и полные ответы на ожидания/альтернативы |
| Сводка | total/scored/unscored, average_score только среди оценённых, распределения баллов/направлений/решений |

Текст в XLSX писать явно как строки, чтобы ответы вида `=...`, `+...` не стали формулами. Не обрезать длинные ответы молча: Excel ограничивает длину ячейки; исполнитель должен разбить текст на продолжения с question_id/answer_id и сохранить весь ответ. Ревизии и is_latest позволяют сделать удобный текущий лист без потери истории.

`request_export(verified_vk_id,recruitment_id,application_id=None,kind='xlsx',filters={},request_key=...)` создаёт pending file и событие с неизменным снимком в одной транзакции. Для общего XLSX scope=cohort и application_id=NULL. Повтор ключа возвращает первый файл; новый фильтр/повторная выгрузка — новый ключ. PDF требует заявку и текущую оценку; PDF всегда связан с конкретной evaluation. Уже готовый PDF не перепривязывается после ручной правки.

## Приватные файлы и история

`FileRepository.reserve_resume(app_id,mime_type=...)` → pending metadata с новым version/object key. `PrivateStorage.upload(metadata,bytes)` загружает; извлечь текст с версией парсера, затем `FileRepository.finish(file_id,size_bytes=...,sha256=...,extracted_text=...,extraction_version=...)`. После ready нельзя менять ни оригинал, ни текст. Для отменённой/ошибочной загрузки оператор/worker переводит pending в failed, после чего пользователь может подать анкету без незавершённого документа; ошибки не содержат исходный документ.

`prepare_history.py` выдаёт приватный JSONL: source row ID, cohort, разрешённые pre-application features, отдельно expert_score. Проверены 57+55=112 размеченных анкет. Не угадываются полные даты. Ни принятие, ни последующие часы/срок участия не входят в features. `evaluate_predictions.py` сопоставляет id/score модели с экспертными и считает coverage, exact_match, MAE; организатор не утверждал эти формулы как официальную метрику. Выделение holdout и обучение — ответственность команды оценки.
