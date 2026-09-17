from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

STREAM_DISCOVERED = "media.discovered"
STREAM_DOWNLOADED = "media.downloaded"
STREAM_READY = "media.ready_to_publish"


@dataclass(frozen=True, slots=True)
class MediaEvent:
    camera_id: str
    external_media_id: str
    media_type: str
    captured_at: str
    source_url: str | None = None
    media_id: str | None = None
    local_path: str | None = None
    sha256: str | None = None
    caption: str | None = None
    analysis_status: str = "disabled"
    event_id: str = ""

    def __post_init__(self) -> None:
        if not self.event_id:
            object.__setattr__(self, "event_id", str(uuid4()))

    @classmethod
    def now(cls, **values: Any) -> "MediaEvent":
        return cls(captured_at=datetime.now(UTC).isoformat(), **values)

    def to_fields(self) -> dict[str, str]:
        return {key: "" if value is None else str(value) for key, value in asdict(self).items()}

    @classmethod
    def from_fields(cls, fields: dict[str, str]) -> "MediaEvent":
        optional = {"source_url", "media_id", "local_path", "sha256", "caption"}
        values = {
            key: None if key in optional and value == "" else value
            for key, value in fields.items()
        }
        return cls(**values)

    def with_media_id(self, media_id: str) -> "MediaEvent":
        values = asdict(self)
        values["media_id"] = media_id
        return MediaEvent(**values)
