import asyncio
import logging
from pathlib import Path

import httpx
from redis.asyncio import Redis

from camera_reposter.bus import EventBus
from camera_reposter.config import Settings
from camera_reposter.events import STREAM_DOWNLOADED
from camera_reposter.store import Store


async def main() -> None:
    settings = Settings.from_environment()
    await Store(settings.database_path).initialize()
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    bus = EventBus(redis)
    logging.info("Telegram publisher started")
    if not settings.telegram_bot_token:
        logging.warning("TELEGRAM_BOT_TOKEN is not configured; publisher is disabled")
        await asyncio.Event().wait()
    async for message_id, event in bus.consume(STREAM_DOWNLOADED, "publishers", "publisher-1"):
        logging.info("Received ready media %s", event.media_id)
        if event.media_id and event.local_path:
            for chat_id in await Store(settings.database_path).pending_deliveries(event.media_id):
                method = "sendVideo" if event.media_type == "video" else "sendPhoto"
                field = "video" if event.media_type == "video" else "photo"
                url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
                async with httpx.AsyncClient(timeout=60) as client:
                    with Path(event.local_path).open("rb") as media_file:
                        response = await client.post(
                            url,
                            data={"chat_id": chat_id, "caption": event.caption or ""},
                            files={field: media_file},
                        )
                    response.raise_for_status()
                    result = response.json().get("result", {})
                await Store(settings.database_path).mark_delivery_sent(
                    event.media_id, chat_id, str(result.get("message_id", ""))
                )
        await bus.acknowledge(STREAM_DOWNLOADED, "publishers", message_id)
    await redis.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
