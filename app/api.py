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
from .models import CaptureImageItem, CaptureRequest, CaptureResponse
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


def get_extra_camera_managers(request: Request) -> list[CameraManager]:
    """Return initialized extra camera managers."""
    managers = getattr(request.app.state, "extra_camera_managers", None)
    if managers is None:
        return []
    return managers


@router.post(
    "/capture",
    response_model=CaptureResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def capture_image(
    capture_request: CaptureRequest | None = Body(default=None),
    settings: Settings = Depends(get_settings),
    camera_manager: CameraManager = Depends(get_camera_manager),
    extra_camera_managers: list[CameraManager] = Depends(get_extra_camera_managers),
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
            "use_extra": payload.use_extra,
        },
    )

    def _capture_and_store(manager: CameraManager, index: int) -> CaptureImageItem:
        frame = manager.capture_fresh_frame(
            resolution=resolution,
            format=image_format,
            quality=quality,
        )
        image = Image.fromarray(frame)
        image_id = uuid4().hex
        file_path = storage.save_image(image, image_id, image_format, quality)
        logger.info("Stored captured image at %s", file_path)
        return CaptureImageItem(
            index=index,
            image_id=image_id,
            image_url_or_path=f"/api/images/{file_path.name}",
        )

    try:
        main_capture = _capture_and_store(camera_manager, index=0)
    except CameraCaptureError as exc:
        logger.exception(
            "Main camera capture failed",
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

    timestamp = datetime.now(timezone.utc)

    if not payload.use_extra:
        return CaptureResponse(
            image_id=main_capture.image_id,
            image_url_or_path=main_capture.image_url_or_path,
            timestamp=timestamp,
        )

    captures: list[CaptureImageItem] = [main_capture]
    for extra_camera_manager in extra_camera_managers:
        try:
            captures.append(_capture_and_store(extra_camera_manager, index=len(captures)))
        except CameraCaptureError as exc:
            logger.warning("Extra camera capture failed; skipping source.", exc_info=exc)

    return CaptureResponse(
        image_id=main_capture.image_id,
        image_url_or_path=main_capture.image_url_or_path,
        timestamp=timestamp,
        images=captures,
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


