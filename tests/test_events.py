from camera_reposter.events import MediaEvent


def test_media_event_round_trip() -> None:
    event = MediaEvent.now(
        camera_id="camera-1",
        external_media_id="file-1",
        media_type="video",
        source_url="https://camera.example/media/file-1",
    )

    restored = MediaEvent.from_fields(event.to_fields())

    assert restored == event