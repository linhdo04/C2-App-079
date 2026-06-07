from redis.asyncio import Redis

from core import settings

redis_client: Redis | None = None


async def init_redis() -> None:
    global redis_client
    redis_client = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )

    await redis_client.ping()


async def close_redis() -> None:
    global redis_client

    if redis_client:
        await redis_client.aclose()


def get_redis() -> Redis:
    if redis_client is None:
        raise RuntimeError("Redis has not been initialized")

    return redis_client
