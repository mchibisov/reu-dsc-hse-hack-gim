"""Закрытое локальное хранилище выгрузок; не имитирует облачный Supabase Storage."""
import asyncio
import hashlib
import os
from pathlib import Path, PurePosixPath
from uuid import uuid4

MAX_SIZE = 20 * 1024 * 1024


class LocalPrivateStorage:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, key):
        if not isinstance(key, str) or not key or '\\' in key or ':' in key:
            raise ValueError('Invalid storage key')
        path = PurePosixPath(key)
        if path.is_absolute() or '..' in path.parts or not path.parts:
            raise ValueError('Invalid storage key')
        resolved = (self.root / Path(*path.parts)).resolve()
        if resolved == self.root or self.root not in resolved.parents:
            raise ValueError('Invalid storage key')
        return resolved

    async def upload(self, metadata, data):
        if metadata['status'] != 'pending' or len(data) > MAX_SIZE:
            raise ValueError('Immutable or oversized object')
        target = self._path(metadata['storage_key'])
        await asyncio.to_thread(self._write_once, target, data)

    def _write_once(self, target, data):
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp = target.with_name('.' + uuid4().hex + '.tmp')
        try:
            with temp.open('xb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temp, target)
            except FileExistsError:
                if target.read_bytes() != data:
                    raise ValueError('Immutable object conflict') from None
        finally:
            temp.unlink(missing_ok=True)

    async def read(self, metadata):
        data = await asyncio.to_thread(self._path(metadata['storage_key']).read_bytes)
        if len(data) > MAX_SIZE or (metadata.get('sha256') and hashlib.sha256(data).hexdigest() != metadata['sha256']):
            raise ValueError('File integrity check failed')
        if metadata.get('size_bytes') is not None and len(data) != metadata['size_bytes']:
            raise ValueError('File size check failed')
        return data

    async def close(self):
        pass
