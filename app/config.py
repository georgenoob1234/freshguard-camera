"""Application configuration for the camera service."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Pydantic settings sourced from environment variables."""

    camera_storage_dir: Path = Field(default=Path("./data/images"))
    camera_default_resolution: str = Field(default="320x320")
    camera_default_format: str = Field(default="jpeg")
    camera_default_quality: int = Field(default=95)
    main_camera_source: str | None = Field(
        default="0",
        description="Primary camera source identifier, e.g. 'dummy', '0', or '/dev/video0'.",
    )
    extra_camera_sources: str = Field(
        default="1",
        description="Optional comma-separated list of additional camera sources.",
    )
    deprecated_camera_source: str | None = Field(
        default=None,
        validation_alias="CAMERA_SOURCE",
        description="Deprecated fallback source; use MAIN_CAMERA_SOURCE instead.",
        exclude=True,
        repr=False,
    )
    used_deprecated_camera_source: bool = Field(default=False, exclude=True, repr=False)
    camera_retention_seconds: int = Field(
        default=3600,
        description="How long to keep captured images on disk before cleanup.",
    )
    camera_cleanup_interval_seconds: int = Field(
        default=600,
        description="Interval between background cleanup passes.",
    )
    camera_warmup_frames: int = Field(
        default=3,
        ge=0,
        description="Number of frames to discard before using a capture.",
    )
    camera_buffer_size: int = Field(
        default=1,
        ge=1,
        description="Requested OpenCV buffer size to minimize stale frames.",
    )

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        case_sensitive=False,
    )

    @field_validator("camera_default_format")
    @classmethod
    def _validate_default_format(cls, value: str) -> str:
        value_lower = value.lower()
        if value_lower not in {"jpeg", "png"}:
            raise ValueError("CAMERA_DEFAULT_FORMAT must be either 'jpeg' or 'png'")
        return value_lower

    @model_validator(mode="after")
    def _resolve_camera_sources(self) -> "Settings":
        main_source = (self.main_camera_source or "").strip()
        if not main_source:
            fallback_source = (self.deprecated_camera_source or "").strip()
            if fallback_source:
                self.main_camera_source = fallback_source
                self.used_deprecated_camera_source = True
                main_source = fallback_source

        if not main_source:
            raise ValueError("MAIN_CAMERA_SOURCE is required.")

        self.main_camera_source = main_source
        self.extra_camera_sources = (self.extra_camera_sources or "").strip()
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    settings = Settings()
    settings.camera_storage_dir.mkdir(parents=True, exist_ok=True)
    return settings

