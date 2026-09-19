from __future__ import annotations

from camera_reposter.adapters.b4hunt import B4HuntCameraAdapter
from camera_reposter.adapters.camera import CameraAdapter
from camera_reposter.config import Settings


def build_camera_adapters(settings: Settings) -> dict[str, CameraAdapter]:
    if not settings.ucon_account or not settings.ucon_account_password:
        return {}
    return {
        "b4hunt": B4HuntCameraAdapter(
            settings.ucon_account,
            settings.ucon_account_password,
            settings.ucon_device_index,
        )
    }
