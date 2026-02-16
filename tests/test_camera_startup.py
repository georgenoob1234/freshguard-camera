"""Startup initialization tests for main and extra camera sources."""

from __future__ import annotations

import logging

import pytest

import app.main as main_module
from app.camera import CameraInitializationError
from app.config import Settings


def test_duplicate_main_and_extra_source_fails_fast() -> None:
    settings = Settings(
        main_camera_source="0",
        extra_camera_sources="/dev/video0",
    )

    with pytest.raises(SystemExit):
        main_module.initialize_camera_managers(settings)


def test_main_camera_initialization_failure_exits_process(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCameraManager:
        def __init__(self, device_index, source, warmup_frames, buffer_size) -> None:
            self.source = source

        def start(self) -> None:
            raise CameraInitializationError("main init failed")

        def stop(self) -> None:
            return None

    monkeypatch.setattr(main_module, "CameraManager", FakeCameraManager)

    settings = Settings(
        main_camera_source="primary-main",
        extra_camera_sources="",
    )

    with pytest.raises(SystemExit):
        main_module.initialize_camera_managers(settings)


def test_extra_camera_failure_warns_and_continues(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FakeCameraManager:
        def __init__(self, device_index, source, warmup_frames, buffer_size) -> None:
            self.source = source

        def start(self) -> None:
            if self.source == "extra-bad":
                raise CameraInitializationError("extra init failed")

        def stop(self) -> None:
            return None

    monkeypatch.setattr(main_module, "CameraManager", FakeCameraManager)

    settings = Settings(
        main_camera_source="primary-main",
        extra_camera_sources="extra-good,extra-bad,extra-good-2",
    )

    with caplog.at_level(logging.WARNING):
        main_manager, extra_managers = main_module.initialize_camera_managers(settings)

    assert main_manager.source == "primary-main"
    assert [manager.source for manager in extra_managers] == ["extra-good", "extra-good-2"]
    assert "Failed to initialize extra camera source; ignoring source." in caplog.text
