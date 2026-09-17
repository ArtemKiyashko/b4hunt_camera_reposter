from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RemoteMedia:
    external_media_id: str
    media_type: str
    captured_at: str
    download_url: str


class CameraAdapter(Protocol):
    async def list_media(self, camera_id: str) -> list[RemoteMedia]: ...
