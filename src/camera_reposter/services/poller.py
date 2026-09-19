import asyncio
import logging

from redis.asyncio import Redis

from camera_reposter.adapters.factory import build_camera_adapters
from camera_reposter.bus import EventBus
from camera_reposter.config import Settings
from camera_reposter.events import STREAM_DISCOVERED, MediaEvent
from camera_reposter.store import Store


async def main() -> None:
    settings = Settings.from_environment()
    await Store(settings.database_path).initialize()
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    bus = EventBus(redis)
    adapters = build_camera_adapters(settings)
    logging.info("Camera poller started for %s camera(s)", len(adapters))
    while True:
        for camera_id, adapter in adapters.items():
            try:
                media_items = await adapter.list_media(camera_id)
            except TimeoutError as error:
                logging.warning("Camera %s SD poll timed out: %s", camera_id, error)
                continue
            logging.info("Camera %s: discovered %d media item(s)", camera_id, len(media_items))
            for media in media_items:
                event = MediaEvent(
                    camera_id=camera_id,
                    external_media_id=media.external_media_id,
                    media_type=media.media_type,
                    captured_at=media.captured_at,
                    source_ref=media.source_ref,
                )
                media_id = await Store(settings.database_path).register_discovered_media(event)
                if media_id:
                    await bus.publish(STREAM_DISCOVERED, event.with_media_id(media_id))
        await asyncio.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
