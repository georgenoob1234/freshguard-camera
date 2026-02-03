"""Pydantic models for the camera service API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class CaptureRequest(BaseModel):
    """Request body for the /capture endpoint."""

    resolution: Optional[str] = Field(
        default=None,
        description='Resolution string formatted as "WIDTHxHEIGHT", e.g. "1920x1080".',
    )
    quality: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="JPEG quality value in the inclusive range [1, 100].",
    )
    format: Optional[Literal["jpeg", "png"]] = Field(
        default=None,
        description='Image format, allowed values are "jpeg" or "png".',
    )

    @field_validator("resolution")
    @classmethod
    def _normalize_resolution(cls, value: Optional[str]) -> Optional[str]:
        return value.lower() if value else value

    @field_validator("format")
    @classmethod
    def _normalize_format(cls, value: Optional[str]) -> Optional[str]:
        return value.lower() if value else value


class CaptureResponse(BaseModel):
    """Response body returned after triggering an image capture."""

    image_id: str = Field(description="Unique identifier for the stored image.")
    image_url_or_path: str = Field(
        description="Relative HTTP path that can be used to download the binary image.",
    )
    timestamp: datetime = Field(description="UTC timestamp for when the capture occurred.")

