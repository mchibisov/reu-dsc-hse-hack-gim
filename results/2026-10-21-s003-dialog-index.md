# S003: журнал проверок private диалога

Все данные тестов синтетические; внешние VK/LLM/Storage API не вызывались. PostgreSQL проверен только на отдельном локальном сервере, три runtime роли применены через SET ROLE оператора. Права отдельных LOGIN/облачной БД и реальная доставка VK этим прогоном не подтверждены.

| Запуск | Изменение/результат | Отчёт |
| --- | --- | --- |
| 01 | RED: новый модуль отсутствует | [01](2026-10-21-s003-dialog-01/report.md) |
| 02 | 10 fake Repository контрактов GREEN | [02](2026-10-21-s003-dialog-02/report.md) |
| 03 | 25/26 GREEN, выявлена неустойчивая XLSX modified date | [03](2026-10-21-s003-dialog-03/report.md) |
| 04 | 26 GREEN после нормализации docProps modified | [04](2026-10-21-s003-dialog-04/report.md) |
| 05 | 27 unit GREEN, DB skipped без DSN; safe conditional fixture | [05](2026-10-21-s003-dialog-05/report.md) |
| 06 | DB не подключена: Windows Proactor несовместим с psycopg | [06](2026-10-21-s003-dialog-06/report.md) |
| 07 | PostgreSQL опрос/replay/submit пройдены, неверные Unicode SQL keys испортили XLSX | [07](2026-10-21-s003-dialog-07/report.md) |
| 08 | Структурная диагностика остановлена Windows stdin encoding | [08](2026-10-21-s003-dialog-08/report.md) |
| 09 | Подтверждены mojibake SQL keys при 22 сохранённых ответах | [09](2026-10-21-s003-dialog-09/report.md) |
| 10 | RED: malformed snapshot раньше сохранялся как пустая XLSX | [10](2026-10-21-s003-dialog-10/report.md) |
| 11 | 28 unit GREEN: fail-closed четырёх ключей до Storage | [11](2026-10-21-s003-dialog-11/report.md) |
| 12 | 29 GREEN без skips после UTF8 bootstrap PostgreSQL | [12](2026-10-21-s003-dialog-12/report.md) |
| 13 | 29 GREEN после лаконичного подтверждения кандидату | [13](2026-10-21-s003-dialog-13/report.md) |
| 14 | RED: отказ оставлял current question пустым и терял следующее согласие | [14](2026-10-21-s003-dialog-14/report.md) |
| 15 | 31 GREEN, отказ→согласие записываются сразу; invalid date/directions исправляются | [15](2026-10-21-s003-dialog-15/report.md) |
| 16 | RED: направленческий вопрос об интересах обходил проверку прошлого опыта | [16](2026-10-21-s003-dialog-16/report.md) |
| 17 | 32 GREEN, только past AND existing experience AND permitted direction | [17](2026-10-21-s003-dialog-17/report.md) |

Файлы реализации: `gim/shared_service.py`, `gim/shared_domain.py`, `gim/shared_xlsx.py`; проверка `tests/test_shared_service.py`.
Контракт: SharedService(bot_repo,worker_repo,staff_repo,vk,settings,storage).handlers — vk.incoming/vk.send/question.send/staff.notify/file.export/application.analyze.
Проверены точный durable binding перед record_answer, исходные ответы целиком, обязательное согласие и 18+, пять кодов направлений или undecided, не более трёх библиотечных уточнений, profile provenance до submit, actual verified VK actor, повторная staff ACL, отключённая оценка, неизменный XLSX snapshot и ready-file reuse.
Ограничение выбора уточнений: детерминированный фильтр библиотечных формулировок не заменяет редакторскую проверку активного банка оператором; модель не вызывается и вопросы не генерируются. При отсутствии описанного опыта либо подходящих past шаблонов уточнений будет ноль.
