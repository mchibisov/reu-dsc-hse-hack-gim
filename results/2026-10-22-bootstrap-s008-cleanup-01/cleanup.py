"""Фиксированная очистка дублирующего runtime, без данных/секретов."""
from pathlib import Path
import json

root=Path(__file__).resolve().parents[2]
config=root/'gim/config.py'
text=config.read_text(encoding='utf-8')
assert '\n@dataclass' in text
config.write_text(text.split('\n@dataclass',1)[0].replace('from dataclasses import dataclass\n','').rstrip()+'\n',encoding='utf-8')
llm=root/'gim/llm.py'
text=llm.read_text(encoding='utf-8')
assert '\n    async def next_question' in text
llm.write_text(text.split('\n    async def next_question',1)[0].replace('from gim.dialog import TASKS\n','').rstrip()+'\n',encoding='utf-8')

test_workflow='''name: Tests
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    strategy:
      matrix:
        include:
          - os: ubuntu-latest
            python: '3.13'
          - os: windows-latest
            python: '3.12'
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
          cache: pip
      - run: python -m pip install -r requirements.shared.txt
      - run: python -m unittest discover -s tests -q
      - run: python -m compileall -q gim api
'''
(root/'.github/workflows/test.yml').write_text(test_workflow,encoding='utf-8')
workflow=root/'.github/workflows/database.yml'
text=workflow.read_text(encoding='utf-8')
start=text.index('      - run: docker build -f Dockerfile.shared')
text=text[:start]+'''      - name: Verify image entry point
        working-directory: .
        run: docker run --rm gim-bot:test python -m gim.shared_main --help
      - name: Verify Compose
        working-directory: .
        run: docker compose --env-file .env.example config --no-env-resolution --quiet
'''
workflow.write_text(text,encoding='utf-8')

for name in ('README.md','docs/setup-from-scratch.md','docs/deployment-guide.md'):
    path=root/name
    text=path.read_text(encoding='utf-8').replace('.env.shared.example','.env.example')
    if name=='docs/setup-from-scratch.md':
        text=text.replace('19 основных вопросов и 11 примеров уточнений','18 основных вопросов и 11 примеров уточнений; исходный DOCX из кейса может содержать прежний вопрос «ВУЗ (Другое)», загрузчик его исключает')
        text=text.replace('"museum-v1"','"museum-v2"')
    if name=='README.md':
        index=text.find('## Старые варианты')
        if index>=0:text=text[:index]+'''## Сохранённая работающая версия

До очистки и изменения анкеты сохранена [«Работающая версия»](https://github.com/mchibisov/reu-dsc-hse-hack-gim/tree/working-version-2026-10-22), commit 7d06b60. Старый public-runtime и его инструкции доступны в этой метке; текущая ветка содержит только private PostgreSQL runtime.

Анкета обновлена: 18 основных вопросов; «ВУЗ (Другое)» удалён, «Факультет, направление» объединён в одно поле. Для существующей БД сначала примените все миграции, включая 20261022030000_questionnaire_revision.sql, затем обновите deployment. Старые ответы сохраняются.
'''
        text=text.replace('Для общего прогона нужны обе тестовые схемы: private-миграции и legacy public-миграции, исключительно в одноразовой БД.','Числа относятся к сохранённой версии S006; после очистки тесты старого public-runtime удалены вместе с ним. Текущий прогон использует только private-миграции в одноразовой БД.')
    path.write_text(text,encoding='utf-8')
print(json.dumps({'trimmed':['gim/config.py: legacy Settings','gim/llm.py: unused next_question/evaluate'],
                  'updated':['CI','README','setup','deployment']},ensure_ascii=False))
