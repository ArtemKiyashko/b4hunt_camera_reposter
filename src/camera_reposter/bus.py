from collections.abc import AsyncIterator

from redis.asyncio import Redis

from camera_reposter.events import MediaEvent


class EventBus:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def publish(self, stream: str, event: MediaEvent) -> str:
        message_id = await self._redis.xadd(stream, event.to_fields())
        return str(message_id)

    async def consume(
        self, stream: str, group: str, consumer: str
    ) -> AsyncIterator[tuple[str, MediaEvent]]:
        try:
            await self._redis.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception as error:
            if "BUSYGROUP" not in str(error):
                raise
        while True:
            result = await self._redis.xreadgroup(
                group, consumer, {stream: ">"}, count=1, block=5000
            )
            for _, messages in result:
                for message_id, fields in messages:
                    decoded = {
                        key.decode() if isinstance(key, bytes) else key: value.decode()
                        if isinstance(value, bytes)
                        else value
                        for key, value in fields.items()
                    }
                    yield str(message_id), MediaEvent.from_fields(decoded)

    async def acknowledge(self, stream: str, group: str, message_id: str) -> None:
        await self._redis.xack(stream, group, message_id)
