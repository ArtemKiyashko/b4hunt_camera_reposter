from pathlib import Path
from uuid import uuid4

import aiosqlite

from camera_reposter.events import MediaEvent

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cameras (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS chat_lists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS chat_list_members (
    chat_list_id TEXT NOT NULL REFERENCES chat_lists(id) ON DELETE CASCADE,
    chat_id TEXT NOT NULL,
    PRIMARY KEY (chat_list_id, chat_id)
);

CREATE TABLE IF NOT EXISTS camera_chat_lists (
    camera_id TEXT NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    chat_list_id TEXT NOT NULL REFERENCES chat_lists(id) ON DELETE CASCADE,
    PRIMARY KEY (camera_id, chat_list_id)
);

CREATE TABLE IF NOT EXISTS media (
    id TEXT PRIMARY KEY,
    camera_id TEXT NOT NULL REFERENCES cameras(id),
    external_media_id TEXT NOT NULL,
    media_type TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    source_url TEXT,
    local_path TEXT,
    sha256 TEXT,
    analysis_status TEXT NOT NULL DEFAULT 'disabled',
    caption TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (camera_id, external_media_id)
);

CREATE TABLE IF NOT EXISTS media_delivery_targets (
    media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    chat_id TEXT NOT NULL,
    PRIMARY KEY (media_id, chat_id)
);

CREATE TABLE IF NOT EXISTS deliveries (
    media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    chat_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    telegram_message_id TEXT,
    telegram_file_id TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    delivered_at TEXT,
    PRIMARY KEY (media_id, chat_id)
);

CREATE TABLE IF NOT EXISTS telegram_files (
    sha256 TEXT NOT NULL,
    media_type TEXT NOT NULL,
    telegram_file_id TEXT NOT NULL,
    PRIMARY KEY (sha256, media_type)
);
"""


class Store:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        Path(self._database_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.executescript(SCHEMA)

    async def register_discovered_media(self, event: MediaEvent) -> str | None:
        media_id = str(uuid4())
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
            cursor = await connection.execute(
                """
                INSERT OR IGNORE INTO media
                    (id, camera_id, external_media_id, media_type, captured_at, source_url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    media_id,
                    event.camera_id,
                    event.external_media_id,
                    event.media_type,
                    event.captured_at,
                    event.source_url,
                ),
            )
            if cursor.rowcount == 0:
                return None
            await connection.execute(
                """
                INSERT INTO media_delivery_targets (media_id, chat_id)
                SELECT ?, members.chat_id
                FROM camera_chat_lists assignments
                JOIN chat_list_members members ON members.chat_list_id = assignments.chat_list_id
                WHERE assignments.camera_id = ?
                ON CONFLICT DO NOTHING
                """,
                (media_id, event.camera_id),
            )
            await connection.execute(
                """
                INSERT INTO deliveries (media_id, chat_id)
                SELECT media_id, chat_id FROM media_delivery_targets WHERE media_id = ?
                """,
                (media_id,),
            )
            await connection.commit()
        return media_id

    async def set_media_downloaded(
        self, media_id: str, local_path: str, sha256: str
    ) -> MediaEvent | None:
        async with aiosqlite.connect(self._database_path) as connection:
            cursor = await connection.execute(
                "UPDATE media SET local_path = ?, sha256 = ? WHERE id = ?",
                (local_path, sha256, media_id),
            )
            if cursor.rowcount == 0:
                return None
            cursor = await connection.execute(
                """SELECT camera_id, external_media_id, media_type, captured_at,
                          source_url, local_path, sha256, caption, analysis_status
                   FROM media WHERE id = ?""",
                (media_id,),
            )
            row = await cursor.fetchone()
            await connection.commit()
        if row is None:
            return None
        return MediaEvent(
            camera_id=row[0], external_media_id=row[1], media_type=row[2],
            captured_at=row[3], source_url=row[4], media_id=media_id,
            local_path=row[5], sha256=row[6], caption=row[7], analysis_status=row[8],
        )

    async def pending_deliveries(self, media_id: str) -> list[str]:
        async with aiosqlite.connect(self._database_path) as connection:
            cursor = await connection.execute(
                "SELECT chat_id FROM deliveries WHERE media_id = ? AND status != 'sent'",
                (media_id,),
            )
            return [row[0] for row in await cursor.fetchall()]

    async def mark_delivery_sent(
        self, media_id: str, chat_id: str, message_id: str | None
    ) -> None:
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute(
                """UPDATE deliveries SET status = 'sent', telegram_message_id = ?,
                          delivered_at = CURRENT_TIMESTAMP
                   WHERE media_id = ? AND chat_id = ?""",
                (message_id, media_id, chat_id),
            )
            await connection.commit()
