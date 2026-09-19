import asyncio
import hashlib
import logging
from pathlib import Path

from redis.asyncio import Redis

from camera_reposter.adapters.camera import RemoteMedia
from camera_reposter.adapters.factory import build_camera_adapters
from camera_reposter.bus import EventBus
from camera_reposter.config import Settings
from camera_reposter.events import STREAM_DISCOVERED, STREAM_DOWNLOADED
from camera_reposter.store import Store


async def main() -> None:
    settings = Settings.from_environment()
    await Store(settings.database_path).initialize()
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    bus = EventBus(redis)
    adapters = build_camera_adapters(settings)
    logging.info("Media downloader started")
    async for message_id, event in bus.consume(STREAM_DISCOVERED, "downloaders", "downloader-1"):
        logging.info("Received %s from camera %s", event.external_media_id, event.camera_id)
        adapter = adapters.get(event.camera_id)
        if not event.media_id or not event.source_ref or adapter is None:
            logging.warning(
                "Skipping media without a configured adapter: %s", event.external_media_id
            )
            await bus.acknowledge(STREAM_DISCOVERED, "downloaders", message_id)
            continue
        target = (
            Path(settings.media_root)
            / event.camera_id
            / f"{event.media_id}.{event.media_type}"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".part")
        await adapter.download_media(
            RemoteMedia(
                event.external_media_id, event.media_type, event.captured_at, event.source_ref
            ),
            temporary,
        )
        digest = hashlib.sha256(temporary.read_bytes())
        temporary.replace(target)
        downloaded = await Store(settings.database_path).set_media_downloaded(
            event.media_id, str(target), digest.hexdigest()
        )
        if downloaded:
            await bus.publish(STREAM_DOWNLOADED, downloaded)
        await bus.acknowledge(STREAM_DISCOVERED, "downloaders", message_id)
    await redis.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
