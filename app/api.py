"""HTTP route definitions for the camera service."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from PIL import Image

from .camera import CameraCaptureError, CameraManager, parse_resolution
from .config import Settings, get_settings
from .models import CaptureRequest, CaptureResponse
from .storage import ImageStorage

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict:
    """Health check endpoint for container orchestration."""
    return {"status": "healthy", "service": "camera"}


def get_storage(settings: Settings = Depends(get_settings)) -> ImageStorage:
    """Dependency provider for ImageStorage."""
    return ImageStorage(settings.camera_storage_dir)


def get_camera_manager(request: Request) -> CameraManager:
    """Return the shared CameraManager stored on the FastAPI app."""
    manager = getattr(request.app.state, "camera_manager", None)
    if manager is None:
        logger.error("Camera manager requested before initialization.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Camera manager is not available.",
        )
    return manager


@router.post("/capture", response_model=CaptureResponse, status_code=status.HTTP_200_OK)
async def capture_image(
    capture_request: CaptureRequest | None = Body(default=None),
    settings: Settings = Depends(get_settings),
    camera_manager: CameraManager = Depends(get_camera_manager),
    storage: ImageStorage = Depends(get_storage),
) -> CaptureResponse:
    """Trigger an image capture and return metadata."""
    payload = capture_request or CaptureRequest()

    resolution_str = payload.resolution or settings.camera_default_resolution
    image_format = payload.format or settings.camera_default_format
    quality = payload.quality or settings.camera_default_quality

    try:
        resolution = parse_resolution(resolution_str)
    except ValueError as exc:
        logger.exception("Failed to parse resolution '%s'", resolution_str)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if image_format not in {"jpeg", "png"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format must be either 'jpeg' or 'png'.",
        )

    logger.info(
        "Processing capture request",
        extra={
            "resolution": f"{resolution[0]}x{resolution[1]}",
            "format": image_format,
            "quality": quality,
        },
    )

    try:
        frame = camera_manager.capture_fresh_frame(
            resolution=resolution,
            format=image_format,
            quality=quality,
        )
    except CameraCaptureError as exc:
        logger.exception(
            "Camera capture failed",
            extra={
                "resolution": f"{resolution[0]}x{resolution[1]}",
                "format": image_format,
                "quality": quality,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Camera capture failed.",
        ) from exc

    image = Image.fromarray(frame)
    image_id = uuid4().hex
    file_path = storage.save_image(image, image_id, image_format, quality)
    timestamp = datetime.now(timezone.utc)

    logger.info("Stored captured image at %s", file_path)

    return CaptureResponse(
        image_id=image_id,
        image_url_or_path=f"/api/images/{file_path.name}",
        timestamp=timestamp,
    )


@router.get("/api/images/{image_filename}")
async def fetch_image(
    image_filename: str,
    storage: ImageStorage = Depends(get_storage),
) -> FileResponse:
    """Serve binary image data for the requested file."""
    file_path = storage.resolve_image_path(image_filename)
    media_type = storage.guess_media_type(file_path)
    return FileResponse(path=file_path, media_type=media_type)


