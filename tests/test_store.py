import aiosqlite

from camera_reposter.events import MediaEvent
from camera_reposter.store import Store


async def test_registration_snapshots_camera_chat_lists(tmp_path) -> None:
    database_path = tmp_path / "state.db"
    store = Store(str(database_path))
    await store.initialize()
    async with aiosqlite.connect(database_path) as connection:
        await connection.executemany(
            "INSERT INTO cameras (id, name) VALUES (?, ?)",
            [("camera-a", "Camera A"), ("camera-b", "Camera B")],
        )
        await connection.execute("INSERT INTO chat_lists (id, name) VALUES ('forest', 'Forest')")
        await connection.executemany(
            "INSERT INTO chat_list_members (chat_list_id, chat_id) VALUES ('forest', ?)",
            [("-1001",), ("-1002",)],
        )
        await connection.execute(
            "INSERT INTO camera_chat_lists (camera_id, chat_list_id) VALUES ('camera-a', 'forest')"
        )
        await connection.commit()

    event = MediaEvent.now(
        camera_id="camera-a",
        external_media_id="item-1",
        media_type="video",
        source_url="https://camera.example/item-1",
    )
    media_id = await store.register_discovered_media(event)

    assert media_id is not None
    assert await store.register_discovered_media(event) is None
    async with aiosqlite.connect(database_path) as connection:
        cursor = await connection.execute(
            "SELECT chat_id FROM media_delivery_targets "
            "WHERE media_id = ? ORDER BY chat_id",
            (media_id,),
        )
        assert await cursor.fetchall() == [("-1001",), ("-1002",)]