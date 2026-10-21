import logging

from .vk import VKError

logger = logging.getLogger(__name__)


async def deliver_reply(store, vk, key):
    if not await store.claim_reply(key):
        return False
    reply = await store.get_reply(key)
    if not reply or reply.user_id is None:
        return False
    try:
        await vk.send(reply.user_id, reply.text, 'outbox:' + key)
    except VKError:
        await store.finish_reply(key, success=False)
        logger.warning('candidate_delivery_deferred key=%s', key)
        return False
    await store.finish_reply(key, success=True)
    return True
