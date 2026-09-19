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
    log_level: str
    ucon_account: str | None
    ucon_account_password: str | None
    ucon_device_index: int

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            redis_url=getenv("REDIS_URL", "redis://localhost:6379/0"),
            database_path=getenv("DATABASE_PATH", "./data/state.db"),
            media_root=getenv("MEDIA_ROOT", "./media"),
            telegram_bot_token=getenv("TELEGRAM_BOT_TOKEN") or None,
            poll_interval_seconds=int(getenv("CAMERA_POLL_INTERVAL_SECONDS", "60")),
            ai_required=getenv("AI_REQUIRED", "false").lower() == "true",
            log_level=getenv("LOG_LEVEL", "INFO").upper(),
            ucon_account=getenv("UBIA_ACCOUNT") or None,
            ucon_account_password=getenv("UBIA_ACCOUNT_PASSWORD") or None,
            ucon_device_index=int(getenv("UBIA_DEVICE_INDEX", "0")),
        )
