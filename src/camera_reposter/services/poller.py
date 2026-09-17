import asyncio
import logging

from camera_reposter.config import Settings
from camera_reposter.store import Store


async def main() -> None:
    settings = Settings.from_environment()
    await Store(settings.database_path).initialize()
    logging.info("Camera poller started; waiting for configured camera adapters")
    while True:
        await asyncio.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
