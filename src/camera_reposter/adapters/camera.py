from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RemoteMedia:
    external_media_id: str
    media_type: str
    captured_at: str
    source_ref: str


class CameraAdapter(Protocol):
    async def list_media(self, camera_id: str) -> list[RemoteMedia]: ...

    async def download_media(self, media: RemoteMedia, destination: Path) -> int: ...
