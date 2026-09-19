from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from p4p_camera_sdk import CredentialClient, RelaySession, SdCardClient, SdCardEvent

from camera_reposter.adapters.camera import RemoteMedia

LOGGER = logging.getLogger(__name__)


class B4HuntCameraAdapter:
    def __init__(self, account: str, password: str, device_index: int = 0) -> None:
        self._credentials = CredentialClient(account, password)
        self._device_index = device_index

    async def _device(self):
        return await self._credentials.get_device(self._device_index)

    async def list_media(self, camera_id: str) -> list[RemoteMedia]:
        device = await self._device()
        begin = int(datetime.now(UTC).timestamp()) - 7 * 24 * 60 * 60
        end = int(datetime.now(UTC).timestamp())
        events = await asyncio.to_thread(
            self._list_events, device.device_uid, device.device_password, begin, end
        )
        LOGGER.info("B4HUNT returned %d SD event(s) for camera %s", len(events), camera_id)
        return [
            RemoteMedia(
                external_media_id=f"{camera_id}:{event.start_time}:{event.src_event}",
                media_type="video",
                captured_at=datetime.fromtimestamp(event.start_time, UTC).isoformat(),
                source_ref=json.dumps({
                    "start_time": event.start_time,
                    "length": event.length,
                    "src_event": event.src_event,
                    "src_status": event.src_status,
                }, separators=(",", ":")),
            )
            for event in events
        ]

    @staticmethod
    def _list_events(uid: str, password: str, begin: int, end: int):
        with RelaySession(uid, password) as session:
            return SdCardClient(session).list_events(begin, end)

    async def download_media(self, media: RemoteMedia, destination: Path) -> int:
        device = await self._device()
        event_values = json.loads(media.source_ref)
        event = SdCardEvent(event_type=0, **event_values)
        return await asyncio.to_thread(
            self._download,
            device.device_uid,
            device.device_password,
            event,
            destination,
        )

    @staticmethod
    def _download(uid: str, password: str, event, destination: Path) -> int:
        with RelaySession(uid, password) as session:
            return SdCardClient(session).download_video(event, destination)
