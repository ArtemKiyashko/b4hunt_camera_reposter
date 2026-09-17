import json
from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True, slots=True)
class Settings:
    redis_url: str
    database_path: str
    media_root: str
    telegram_bot_token: str | None
    poll_interval_seconds: int
    ai_required: bool
    cameras_json: str
    log_level: str

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            redis_url=getenv("REDIS_URL", "redis://localhost:6379/0"),
            database_path=getenv("DATABASE_PATH", "./data/state.db"),
            media_root=getenv("MEDIA_ROOT", "./media"),
            telegram_bot_token=getenv("TELEGRAM_BOT_TOKEN") or None,
            poll_interval_seconds=int(getenv("CAMERA_POLL_INTERVAL_SECONDS", "60")),
            ai_required=getenv("AI_REQUIRED", "false").lower() == "true",
            cameras_json=getenv("CAMERAS_JSON", "[]"),
            log_level=getenv("LOG_LEVEL", "INFO").upper(),
        )

    def cameras(self) -> list[dict[str, str]]:
        value = json.loads(self.cameras_json)
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise ValueError("CAMERAS_JSON must be a JSON array of objects")
        return value
