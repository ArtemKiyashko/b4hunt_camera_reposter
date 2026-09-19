# Camera Reposter

Asynchronous pipeline that discovers media from remote cameras and delivers it to assigned Telegram chat lists.

## Services

- `camera-poller`: discovers new camera files and publishes `media.discovered`.
- `media-downloader`: persists media locally and publishes `media.ready_to_publish` while AI is disabled.
- `telegram-publisher`: delivers each media item once per allowed chat and reuses Telegram `file_id`.
- `redis`: durable event transport using Redis Streams.

The P4P implementation belongs in a separate SDK boundary. It is useful for
this UBox/Ucon SDK family, but it is not a generic camera driver: relay
behavior, event codes, file framing, and firmware capabilities vary by model.
This application depends only on the small camera adapter contract; the
reusable `p4p-camera-sdk` is published and versioned independently.

The database is SQLite in the `app-data` Docker volume. Downloaded media resides in `media`.

## Run

```sh
cp .env.example .env
# Configure UBIA_ACCOUNT, UBIA_ACCOUNT_PASSWORD and UBIA_DEVICE_INDEX first.
# UBIA_DEVICE_INDEX is the camera position in the Ucon app and starts at 0.
docker compose pull
docker compose up -d

# Follow service logs
docker compose logs -f camera-poller media-downloader telegram-publisher

# For local source/image development, build explicitly:
docker compose build
```

The camera adapter is isolated in `src/camera_reposter/adapters/camera.py`.
The reverse-engineering work has been removed from this runtime repository and
is maintained in the separately versioned `p4p-camera-sdk` repository.

The pinned SDK version is declared in `pyproject.toml`; Docker installs it
from the package index as part of the normal application build.

## Event flow

`media.discovered` -> `media.downloaded` -> `media.ready_to_publish`

When AI is enabled, the analyzer will consume `media.downloaded` and must produce `media.ready_to_publish` after either successful analysis or a terminal analysis failure.

## Research versus production

Protocol research, captures, decompiled APK output, replay scripts, and
extracted media are intentionally outside this application repository. The
The verified P4P implementation is published as a separately versioned SDK,
then injected through `CameraAdapter` without
coupling the Telegram pipeline to protocol internals.

## Production checklist

- Keep camera credentials in a secret store or protected `.env`; never commit them.
- Pin and review dependencies before publishing images.
- Set `UBIA_DEVICE_INDEX` to the zero-based camera position shown by the Ucon app.
- Add Telegram rate limiting, retry/backoff, and webhook/alerting for failed deliveries.
- Publish the P4P SDK separately only after protocol tests cover relay discovery,
  event decoding, multi-file downloads, and incomplete-transfer recovery.
