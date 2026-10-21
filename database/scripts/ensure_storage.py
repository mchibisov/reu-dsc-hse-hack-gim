import asyncio
import os
from gim_db.storage import PrivateStorage
async def main():
    s=PrivateStorage(os.environ['SUPABASE_URL'],os.environ['SUPABASE_STORAGE_KEY'])
    try:await s.ensure_bucket()
    finally:await s.close()
    print('Private bucket verified')
asyncio.run(main())
