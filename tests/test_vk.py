import httpx

from gim_bot.config import Settings
from gim_bot.vk import VKClient


async def test_vk_send_retries_with_stable_random_id():
    requests = []

    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={'error': {'error_code': 6}})
        return httpx.Response(200, json={'response': 12})

    client = VKClient(Settings(vk_token='secret'), transport=httpx.MockTransport(respond), rate_interval=0)
    await client.send(123, 'Принято', 'unique-event')
    assert len(requests) == 2
    assert requests[0].content == requests[1].content
    assert 'access_token' not in str(requests[0].url)
    await client.close()


async def test_uploads_excel_and_sends_document():
    paths = []

    def respond(request):
        paths.append(request.url.path)
        if request.url.path.endswith('docs.getMessagesUploadServer'):
            data = {'response': {'upload_url': 'https://upload.vk.com/doc'}}
        elif request.url.host == 'upload.vk.com':
            assert b'fake-xlsx' in request.content
            data = {'file': 'uploaded-file'}
        elif request.url.path.endswith('docs.save'):
            data = {'response': {'type': 'doc', 'doc': {'owner_id': 1, 'id': 2, 'access_key': 'key'}}}
        else:
            data = {'response': 123}
        return httpx.Response(200, json=data)

    client = VKClient(Settings(vk_token='secret'), transport=httpx.MockTransport(respond), rate_interval=0)
    attachment = await client.upload_document(999, b'fake-xlsx', 'gim.xlsx')
    assert attachment == 'doc1_2_key'
    await client.send(999, 'Выгрузка', 'export-1', attachment=attachment)
    assert paths[-1].endswith('messages.send')
    await client.close()
