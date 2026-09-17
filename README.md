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
reusable `p4p-camera-sdk` will be published and versioned independently.

The database is SQLite in the `app-data` Docker volume. Downloaded media resides in `media`.

## Run

```sh
cp .env.example .env
docker compose up -d --build

# Follow service logs
docker compose logs -f camera-poller media-downloader telegram-publisher
```

The camera adapter is isolated in `src/camera_reposter/adapters/camera.py`.
The reverse-engineering work has been removed from this runtime repository and
is being extracted into the separately versioned SDK.

## Event flow

`media.discovered` -> `media.downloaded` -> `media.ready_to_publish`

When AI is enabled, the analyzer will consume `media.downloaded` and must produce `media.ready_to_publish` after either successful analysis or a terminal analysis failure.

## Research versus production

Protocol research, captures, decompiled APK output, replay scripts, and
extracted media are intentionally outside this application repository. The
next production milestone is to publish the verified P4P implementation as a
separately versioned SDK, then inject it through `CameraAdapter` without
coupling the Telegram pipeline to protocol internals.

## Production checklist

- Keep camera credentials in a secret store or protected `.env`; never commit them.
- Pin and review dependencies before publishing images.
- Add a real camera adapter configuration and migrations before enabling polling.
- Add Telegram rate limiting, retry/backoff, and webhook/alerting for failed deliveries.
- Publish the P4P SDK separately only after protocol tests cover relay discovery,
  event decoding, multi-file downloads, and incomplete-transfer recovery.
