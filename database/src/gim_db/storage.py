"""Private, immutable storage objects. Signed URLs are created only after staff checks."""
from uuid import uuid4
from urllib.parse import quote
import httpx
from .repository import app_lock, one, audit

MAX_SIZE=20*1024*1024
RESUME_MIMES={'application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document','text/plain'}


class StorageError(RuntimeError): pass


class PrivateStorage:
    def __init__(self,url,key,*,bucket='gim-private',client=None):
        self.url=url.rstrip('/')
        self.key=key
        self.bucket=bucket
        self.client=client or httpx.AsyncClient(timeout=30)
        self._owns_client=client is None

    @property
    def headers(self):
        return {'apikey':self.key,'Authorization':f'Bearer {self.key}'}

    async def close(self):
        if self._owns_client: await self.client.aclose()

    async def ensure_bucket(self):
        r=await self.client.get(f'{self.url}/storage/v1/bucket/{self.bucket}',headers=self.headers)
        if r.status_code==404:
            r=await self.client.post(f'{self.url}/storage/v1/bucket',headers=self.headers,json={
                'id':self.bucket,'name':self.bucket,'public':False,'file_size_limit':MAX_SIZE,
                'allowed_mime_types':sorted(RESUME_MIMES|{'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})})
        if r.is_error: raise StorageError(f'bucket_status_{r.status_code}')
        data=r.json()
        if data.get('public'): raise StorageError('bucket_must_be_private')
        # Readback is authoritative; never silently turn someone else's public bucket private.
        r=await self.client.get(f'{self.url}/storage/v1/bucket/{self.bucket}',headers=self.headers)
        if r.is_error or r.json().get('public') is not False: raise StorageError('private_bucket_verification_failed')

    def path(self,key):
        if key.startswith('/') or '..' in key.split('/'): raise ValueError('Invalid object path')
        return f'{quote(self.bucket,safe="")}/{quote(key,safe="/")}'

    async def upload(self,metadata,data: bytes):
        if len(data)>MAX_SIZE: raise ValueError('File too large')
        if metadata['status']!='pending': raise ValueError('Immutable ready object')
        r=await self.client.post(f'{self.url}/storage/v1/object/{self.path(metadata["storage_key"])}',
            headers={**self.headers,'Content-Type':metadata['mime_type'],'x-upsert':'false'},content=data)
        if r.status_code in (400,409):
            # Retry after crash: accept an existing object only after comparing bytes.
            existing=await self.client.get(f'{self.url}/storage/v1/object/authenticated/{self.path(metadata["storage_key"])}',headers=self.headers)
            if existing.is_error or existing.content!=data: raise StorageError('object_conflict')
        elif r.is_error: raise StorageError(f'upload_status_{r.status_code}')

    async def signed_url(self,staff_repository,verified_vk_id,file_id,*,expires_in=60):
        if not 1<=expires_in<=300: raise ValueError('Signed URL lifetime must be 1..300s')
        meta=await staff_repository.staff_file(verified_vk_id,file_id)
        r=await self.client.post(f'{self.url}/storage/v1/object/sign/{self.path(meta["storage_key"])}',
            headers=self.headers,json={'expiresIn':expires_in})
        if r.is_error: raise StorageError(f'sign_status_{r.status_code}')
        # Caller must not persist/log the URL. Previously issued URLs expire; revocation is not retroactive.
        signed=r.json()['signedURL']
        return signed if signed.startswith('https://') else self.url+'/storage/v1'+signed


class FileRepository:
    def __init__(self,pool): self.pool=pool

    async def reserve_resume(self,app_id,*,mime_type):
        if mime_type not in RESUME_MIMES: raise ValueError('Unsupported resume format')
        async with self.pool.connection() as c, c.transaction():
            a=await app_lock(c,app_id)
            if a['status']!='draft': raise ValueError('Resume must be uploaded before submission')
            v=await one(c,"SELECT COALESCE(max(version),0)+1 AS n FROM gim.files WHERE application_id=%s AND kind='resume'",(app_id,))
            fid=uuid4()
            return await one(c,'''INSERT INTO gim.files(id,application_id,recruitment_id,kind,scope,version,storage_key,mime_type)
                VALUES(%s,%s,%s,'resume','candidate',%s,%s,%s) RETURNING *''',
                (fid,app_id,a['recruitment_id'],v['n'],f'{a["recruitment_id"]}/{app_id}/{fid}',mime_type))

    async def finish(self,file_id,*,size_bytes,sha256,extracted_text=None,extraction_version=None):
        if not 0<=size_bytes<=MAX_SIZE: raise ValueError('Invalid file size')
        async with self.pool.connection() as c, c.transaction():
            # App first, then file: same lock order as answer/evaluation to avoid deadlocks.
            f=await one(c,'SELECT * FROM gim.files WHERE id=%s',(file_id,))
            if not f: raise LookupError('File not found')
            if f['application_id']:
                if f['kind']=='xlsx':
                    # Explicit staff audit exports may read archived attempts; never edit their answers.
                    await one(c,'SELECT id FROM gim.applications WHERE id=%s FOR UPDATE',(f['application_id'],))
                else:
                    await app_lock(c,f['application_id'])
            f=await one(c,'SELECT * FROM gim.files WHERE id=%s FOR UPDATE',(file_id,))
            if f['status']=='ready':
                if (f['sha256'],f['size_bytes'],f['extracted_text'],f['extraction_version'])==(sha256,size_bytes,extracted_text,extraction_version): return f
                raise ValueError('Ready file is immutable')
            f=await one(c,"""UPDATE gim.files SET status='ready',size_bytes=%s,sha256=%s,extracted_text=%s,extraction_version=%s
                WHERE id=%s RETURNING *""",(size_bytes,sha256,extracted_text,extraction_version,file_id))
            await audit(c,f['application_id'],'file.ready',{'file_id':str(file_id),'version':f['version']})
            return f
