"""Integration tests for the /capture endpoint defaults."""

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from app.api import get_camera_manager, get_extra_camera_managers
from app.config import Settings, get_settings
from app.main import app


def override_settings(tmp_path: Path) -> Settings:
    """Utility to create deterministic settings for tests."""
    return Settings(
        camera_storage_dir=tmp_path,
        camera_default_resolution="320x320",
        camera_default_format="jpeg",
        camera_default_quality=95,
        main_camera_source="dummy",
        extra_camera_sources="",
        camera_warmup_frames=1,
        camera_buffer_size=1,
    )


def test_capture_defaults(tmp_path):
    settings = override_settings(tmp_path)

    def _override_settings():
        return settings

    app.dependency_overrides[get_settings] = _override_settings
    try:
        with TestClient(app) as client:
            response = client.post("/capture", json={})

        assert response.status_code == 200
        payload = response.json()

        assert payload["image_url_or_path"].startswith("/api/images/")
        assert "images" not in payload
        assert Path(settings.camera_storage_dir / Path(payload["image_url_or_path"]).name).exists()

        timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
        assert timestamp.tzinfo == timezone.utc
    finally:
        app.dependency_overrides.clear()


def test_capture_invokes_camera_manager_once(tmp_path):
    settings = override_settings(tmp_path)

    class DummyManager:
        def __init__(self):
            self.calls = 0

        def capture_fresh_frame(self, resolution, format, quality):
            self.calls += 1
            width, height = resolution
            return np.zeros((height, width, 3), dtype=np.uint8)

    dummy_manager = DummyManager()

    def _override_settings():
        return settings

    app.dependency_overrides[get_settings] = _override_settings
    app.dependency_overrides[get_camera_manager] = lambda: dummy_manager

    try:
        with TestClient(app) as client:
            response = client.post("/capture", json={})
            assert response.status_code == 200
            payload = response.json()

        assert dummy_manager.calls == 1
        stored_file = settings.camera_storage_dir / Path(payload["image_url_or_path"]).name
        assert stored_file.exists()
    finally:
        app.dependency_overrides.clear()


def test_capture_use_extra_includes_images_array(tmp_path):
    settings = override_settings(tmp_path)

    class DummyMainManager:
        def capture_fresh_frame(self, resolution, format, quality):
            width, height = resolution
            return np.zeros((height, width, 3), dtype=np.uint8)

    class DummyExtraManager:
        def capture_fresh_frame(self, resolution, format, quality):
            width, height = resolution
            return np.ones((height, width, 3), dtype=np.uint8)

    main_manager = DummyMainManager()
    extra_managers = [DummyExtraManager()]

    def _override_settings():
        return settings

    app.dependency_overrides[get_settings] = _override_settings
    app.dependency_overrides[get_camera_manager] = lambda: main_manager
    app.dependency_overrides[get_extra_camera_managers] = lambda: extra_managers

    try:
        with TestClient(app) as client:
            response = client.post("/capture", json={"use_extra": True})
            assert response.status_code == 200
            payload = response.json()

        assert "images" in payload
        assert len(payload["images"]) == 2
        assert payload["images"][0]["index"] == 0
        assert payload["images"][1]["index"] == 1
        assert payload["image_id"] == payload["images"][0]["image_id"]
        assert payload["image_url_or_path"] == payload["images"][0]["image_url_or_path"]
    finally:
        app.dependency_overrides.clear()

