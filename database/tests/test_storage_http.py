import httpx
import pytest
from gim_db.storage import PrivateStorage,StorageError


async def test_private_bucket_and_no_upsert_and_short_url():
    calls=[]
    def responder(request):
        calls.append(request)
        if request.url.path=='/storage/v1/bucket/gim-private':return httpx.Response(200,json={'id':'gim-private','public':False})
        if '/object/sign/' in request.url.path:return httpx.Response(200,json={'signedURL':'/object/sign/gim-private/opaque?token=synthetic'})
        return httpx.Response(200,json={'Key':'gim-private/opaque'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as client:
        s=PrivateStorage('https://example.invalid','synthetic-key',client=client)
        await s.ensure_bucket()
        await s.upload({'status':'pending','storage_key':'opaque','mime_type':'text/plain'},b'synthetic')
        assert calls[-1].headers['x-upsert']=='false'
        class Staff:
            async def staff_file(self,vk,fid):
                if vk!=1:raise PermissionError()
                return {'storage_key':'opaque'}
        with pytest.raises(PermissionError):await s.signed_url(Staff(),2,'id')
        url=await s.signed_url(Staff(),1,'id')
        assert url.startswith('https://example.invalid/storage/v1/object/sign/')
        with pytest.raises(ValueError):await s.signed_url(Staff(),1,'id',expires_in=600)
        with pytest.raises(ValueError):s.path('../escape')
