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
    use_extra: bool = Field(
        default=False,
        description="When true, capture from main and all initialized extra cameras.",
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
    images: Optional[list["CaptureImageItem"]] = Field(
        default=None,
        description="All captured images when use_extra=true; main camera is index 0.",
    )


class CaptureImageItem(BaseModel):
    """Image metadata for one camera capture in a multi-camera response."""

    index: int = Field(ge=0, description="Zero-based capture index in this response.")
    image_id: str = Field(description="Unique identifier for the stored image.")
    image_url_or_path: str = Field(
        description="Relative HTTP path that can be used to download the binary image.",
    )

