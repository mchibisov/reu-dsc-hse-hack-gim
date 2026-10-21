from gim_bot.storage import Store

ANSWERS = {
    'name': 'Тестовый Кандидат', 'email': 'example@example.org',
    'vk_link': 'https://vk.com/id123', 'birth_date': '01.01.2000',
    'status': 'работаю', 'university': 'не учусь', 'faculty': 'не относится',
    'course': 'не относится', 'interests': 'История Москвы',
    'experience': 'Снимал мероприятия в музее, отбирал фотографии.',
    'languages': 'Английский B2', 'motivation': 'Хочу помогать Историческому музею',
    'expectations': 'Получить опыт музейной фотографии', 'hours': '10',
    'hobbies': 'Фотография', 'directions': 'медиа', 'source': 'друзья',
}


async def finish(store, uid=123):
    await store.handle_message(uid, 'start', '/start')
    await store.handle_message(uid, 'consent', 'Согласен')
    for i in range(40):
        app = await store.get_by_user(uid)
        if app.status == 'completed':
            return app
        key = await store.current_key(uid)
        await store.handle_message(uid, f'answer-{i}', ANSWERS.get(key, 'Снимал музейные события камерой.'))
    raise AssertionError('Анкета не завершилась')


async def test_no_application_before_consent(store):
    reply = await store.handle_message(123, '1', '/start')
    assert 'соглас' in reply.text.lower()
    assert await store.get_by_user(123) is None
    await store.handle_message(123, '2', 'Не согласен')
    assert await store.get_by_user(123) is None


async def test_full_dialog_preserves_fields_and_only_confirms(store):
    app = await finish(store)
    assert app.answers['experience'] == ANSWERS['experience']
    assert app.answers['directions'] == 'медиа'
    assert app.answers['university'] == 'не учусь'
    assert app.answers['faculty'] == 'не относится'
    assert app.score is None
    assert 1 <= len(app.followups) <= 3
    assert all(item['answer'] for item in app.followups)
    result = await store.handle_message(123, 'again', '/start')
    assert 'получена' in result.text.lower()
    assert 'балл' not in result.text.lower()


async def test_duplicate_event_and_restart(store):
    await store.handle_message(123, '1', 'Согласен')
    first = await store.handle_message(123, '2', ANSWERS['name'])
    again = await store.handle_message(123, '2', ANSWERS['name'])
    assert first == again
    assert await store.current_key(123) == 'email'
    reopened = Store(store.database_url)
    await reopened.initialize()
    assert await reopened.current_key(123) == 'email'
    await reopened.close()


async def test_invalid_email_does_not_advance(store):
    await store.handle_message(123, '1', 'Согласен')
    await store.handle_message(123, '2', ANSWERS['name'])
    reply = await store.handle_message(123, '3', 'не email')
    assert 'email' in reply.text.lower()
    assert await store.current_key(123) == 'email'


async def test_delete_requires_confirmation(store):
    await store.handle_message(123, '1', 'Согласен')
    await store.handle_message(123, '2', '/delete')
    assert await store.get_by_user(123) is not None
    await store.handle_message(123, '3', 'УДАЛИТЬ')
    assert await store.get_by_user(123) is None


async def test_fund_expectations_and_alternatives(store):
    from gim_bot.questionnaire import select_followups
    questions = select_followups({'directions': 'фондовое', 'experience': 'Работал в архиве'})
    assert any('альтернатив' in q['question'].lower() or 'другие направления' in q['question'].lower()
               for q in questions)
    assert not any('фото' in q['question'].lower() for q in questions)


async def test_student_keeps_other_university_faculty_and_course(store, monkeypatch):
    for key, value in {'status': 'студент', 'university': 'другое', 'university_other': 'Тестовый университет',
                       'faculty': 'Исторический факультет', 'course': '2'}.items():
        monkeypatch.setitem(ANSWERS, key, value)
    app = await finish(store)
    assert app.answers['university_other'] == 'Тестовый университет'
    assert app.answers['faculty'] == 'Исторический факультет'
    assert app.answers['course'] == '2'
