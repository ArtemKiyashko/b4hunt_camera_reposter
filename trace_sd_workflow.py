"""Trace the complete Ucon SD workflow without changing production code."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import struct
from datetime import UTC, datetime, timedelta
from pathlib import Path

from p4p_camera_sdk import CredentialClient
from p4p_camera_sdk.relay import RDT_IOTYPE_BASE, RelaySession, build_ioctrl_frame
from p4p_camera_sdk.sdcard import (
    FILE_TYPE_VIDEO,
    IOTYPE_DOWNLOAD_VIDEO_FILE_REQ,
    IOTYPE_GET_ADVANCE_SETTINGS_REQ,
    IOTYPE_LISTEVENT_REQ,
    IOTYPE_RECORD_BITMAP_REQ,
    IOTYPE_VIDEO_FILE_DATA_REQ,
    VIDEO_FILE_DATA_CHUNK_SIZE,
    build_download_sd_file,
    build_event_calendar,
    build_list_event,
    build_video_file_data,
    parse_rdt_event_records,
)

LOG = logging.getLogger("ucon-trace")
FILENAME_RE = re.compile(rb"20\d{6}_\d{6}_\d{3}_\d{3}_N\.[A-Za-z+]+")


def describe(iotype: int) -> str:
    if iotype >= RDT_IOTYPE_BASE:
        return f"RDT:0x{iotype - RDT_IOTYPE_BASE:x}"
    return f"IOCTL:{iotype}"


def dump_frame(output: Path, index: int, iotype: int, data: bytes) -> None:
    name = output / f"{index:05d}_{iotype:08x}.bin"
    name.write_bytes(data)
    names = [match.decode("ascii", "replace") for match in FILENAME_RE.findall(data)]
    ascii_text = "".join(chr(value) if 32 <= value < 127 else "." for value in data[:96])
    LOG.info(
        "<- %s len=%d hex=%s ascii=%r names=%s",
        describe(iotype), len(data), data[:48].hex(), ascii_text, names,
    )


def collect(
    session: RelaySession, output: Path, timeout: float, label: str
) -> list[tuple[int, bytes]]:
    LOG.info("collect %s for %.1fs", label, timeout)
    frames: list[tuple[int, bytes]] = []
    for index, (iotype, data) in enumerate(session.poll_ioctrl(timeout=timeout)):
        dump_frame(output, index, iotype, data)
        frames.append((iotype, data))
    LOG.info("%s: %d frames", label, len(frames))
    return frames


def send(session: RelaySession, iotype: int, payload: bytes) -> None:
    LOG.info("-> IOCTL:%d len=%d hex=%s", iotype, len(payload), payload[:64].hex())
    session.send_ioctrl(0, iotype, payload)


def send_initial_settings_batch(session: RelaySession) -> None:
    assert session.kcp is not None
    LOG.info("-> IOCTL:960 + IOCTL:8474 initial SD/live batch")
    session.kcp.enqueue(build_ioctrl_frame(0, IOTYPE_GET_ADVANCE_SETTINGS_REQ, bytes(4)))
    session.kcp.enqueue(build_ioctrl_frame(0, 0x211A, bytes(4)))
    session.kcp.update(session._clock())
    session.kcp.flush()


def parse_timestamp(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def extract_events(frames: list[tuple[int, bytes]]) -> list[tuple[int, int, int, int, int]]:
    events: list[tuple[int, int, int, int, int]] = []
    for iotype, data in frames:
        if iotype != RDT_IOTYPE_BASE + 0x04:
            continue
        for record in parse_rdt_event_records(data):
            item = (
                record.start_time, record.length, record.src_event,
                record.src_status, record.event_type,
            )
            if item not in events:
                events.append(item)
    return events


def download_first(
    session: RelaySession, output: Path, event: tuple[int, int, int, int, int]
) -> None:
    start_time, length, src_event, src_status, _ = event
    send(
        session,
        IOTYPE_DOWNLOAD_VIDEO_FILE_REQ,
        build_download_sd_file(FILE_TYPE_VIDEO, start_time, length, src_event, src_status),
    )
    collect(session, output, 5, "download metadata")

    content = bytearray()
    offset = 0
    while True:
        request_size = VIDEO_FILE_DATA_CHUNK_SIZE
        send(
            session,
            IOTYPE_VIDEO_FILE_DATA_REQ,
                build_video_file_data(
                    FILE_TYPE_VIDEO, start_time, 0, offset, request_size,
                    seq=offset // request_size,
                ),
        )
        frames = collect(session, output, 5, f"file block offset={offset}")
        block = None
        for iotype, data in frames:
            if iotype != RDT_IOTYPE_BASE + 0x1000004 or len(data) < 8:
                continue
            block_offset, block_size = struct.unpack_from("<II", data, 0)
            if block_offset == offset and 0 < block_size <= len(data) - 8:
                block = data[8:8 + block_size]
                break
        if block is None:
            LOG.warning("no file block at offset %d", offset)
            break
        content.extend(block)
        offset += len(block)
        if len(block) < request_size:
            break
        if offset > 100 * 1024 * 1024:
            raise RuntimeError("trace transfer exceeded 100 MiB")
    target = output / "first-event.bin"
    target.write_bytes(content)
    LOG.info("saved %d bytes to %s", len(content), target)


def replay_captured_video_request(session: RelaySession, output: Path) -> None:
    """Replay the first confirmed video request from the official-app capture."""
    send(
        session,
        IOTYPE_DOWNLOAD_VIDEO_FILE_REQ,
        bytes.fromhex("00000000000100003e036dac820f0c10"),
    )
    collect(session, output, 5, "captured video metadata")
    timestamp = int.from_bytes(bytes.fromhex("2fceab6a"), "little")
    send(
        session,
        IOTYPE_VIDEO_FILE_DATA_REQ,
        build_video_file_data(FILE_TYPE_VIDEO, timestamp, 0, 0, VIDEO_FILE_DATA_CHUNK_SIZE),
    )
    collect(session, output, 8, "captured video first block")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--begin", default=(datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%d")
    )
    parser.add_argument("--end", default=datetime.now(UTC).strftime("%Y-%m-%d"))
    parser.add_argument("--output", default="/tmp/ucon-sd-trace")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--pre-sd-wait", type=float, default=0.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    account = os.environ.get("UBIA_ACCOUNT")
    password = os.environ.get("UBIA_ACCOUNT_PASSWORD")
    if not account or not password:
        raise SystemExit("UBIA_ACCOUNT and UBIA_ACCOUNT_PASSWORD must be exported")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    credentials = await CredentialClient(account, password).get_device(0)
    LOG.info(
        "device resolved: uid length=%d name=%r",
        len(credentials.device_uid), credentials.device_name,
    )
    with RelaySession(credentials.device_uid, credentials.device_password) as session:
        if args.pre_sd_wait > 0:
            LOG.info("pre-SD live wait for %.1fs", args.pre_sd_wait)
            collect(session, output, args.pre_sd_wait, "pre-SD live wait")

        LOG.info("step 1: initial SD/live settings batch")
        # Frida-confirmed Ucon UX flow after live view is available: entering
        # SD playback starts with 960 and companion 0x211a before SD commands.
        send_initial_settings_batch(session)
        event_frames = collect(session, output, 5, "advance settings")

        LOG.info("step 2: SD entry stop variant -> event list -> settings refresh")
        # There are two command=2 variants. Ucon uses playrecord=0,param=0 when
        # entering SD/list flow, and playrecord=1,param=1 later when stopping
        # playback/closing the SD flow.
        LOG.info("-> AVCTRL SD entry command=2 playrecord=0 param=0")
        session.send_avctrl(2, playrecord=0, streamindex=0, with_audio=1, param=0)
        send(
            session, IOTYPE_LISTEVENT_REQ,
            build_list_event(parse_timestamp(args.begin), parse_timestamp(args.end)),
        )
        send(session, IOTYPE_GET_ADVANCE_SETTINGS_REQ, bytes(4))
        event_frames.extend(collect(session, output, 15, "event list"))
        for attempt in range(2):
            LOG.info("repeat event-list attempt %d", attempt + 1)
            LOG.info("-> AVCTRL SD entry command=2 playrecord=0 param=0")
            session.send_avctrl(2, playrecord=0, streamindex=0, with_audio=1, param=0)
            send(
                session, IOTYPE_LISTEVENT_REQ,
                build_list_event(parse_timestamp(args.begin), parse_timestamp(args.end)),
            )
            send(session, IOTYPE_GET_ADVANCE_SETTINGS_REQ, bytes(4))
            event_frames.extend(collect(session, output, 8, f"event list repeat {attempt + 1}"))

        LOG.info("step 3: event calendar")
        send(
            session, IOTYPE_RECORD_BITMAP_REQ,
            build_event_calendar(parse_timestamp(args.begin), parse_timestamp(args.end)),
        )
        collect(session, output, 8, "calendar")

        events = extract_events(event_frames)
        LOG.info("parsed events: %s", events[:20])
        if args.download and events:
            download_first(session, output, events[0])
        elif args.download:
            replay_captured_video_request(session, output)


if __name__ == "__main__":
    asyncio.run(main())
