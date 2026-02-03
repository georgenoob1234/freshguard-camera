"""FastAPI application factory for the camera service."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
import inspect

from fastapi import FastAPI

from .api import router
from .camera import CameraInitializationError, CameraManager
from .config import Settings, get_settings

logger = logging.getLogger(__name__)


async def cleanup_loop(settings: Settings) -> None:
    """Background task that deletes expired images on a fixed interval."""
    storage_dir = settings.camera_storage_dir
    storage_dir.mkdir(parents=True, exist_ok=True)

    try:
        while True:
            try:
                cutoff = time.time() - settings.camera_retention_seconds
                deleted = 0

                for path in storage_dir.glob("*"):
                    if not path.is_file():
                        continue

                    try:
                        if path.stat().st_mtime < cutoff:
                            path.unlink()
                            deleted += 1
                    except Exception as exc:
                        logger.warning(
                            "Failed to delete old image",
                            extra={"path": str(path), "error": str(exc)},
                        )

                if deleted > 0:
                    logger.info(
                        "Camera cleanup removed old images",
                        extra={"deleted": deleted},
                    )
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.error("Camera cleanup loop error", extra={"error": str(exc)})

            await asyncio.sleep(settings.camera_cleanup_interval_seconds)
    except asyncio.CancelledError:  # pragma: no cover - cleanup path
        logger.info("Cleanup loop cancelled")
        raise


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    logging.basicConfig(level=logging.INFO)
    app = FastAPI(
        title="Camera Service",
        description="Passive camera microservice used by the Brain orchestrator.",
        version="0.1.0",
    )
    app.include_router(router)
    app.state.camera_manager = None
    app.state.cleanup_task = None

    async def _resolve_settings() -> Settings:
        override = app.dependency_overrides.get(get_settings)
        if override is None:
            return get_settings()

        candidate = override()
        if inspect.isawaitable(candidate):
            return await candidate
        return candidate

    @app.on_event("startup")
    async def start_services() -> None:
        """Start the camera manager and background cleanup loop."""
        settings = await _resolve_settings()
        device_index = int(settings.camera_source) if settings.camera_source.isdigit() else 0
        camera_manager = CameraManager(
            device_index=device_index,
            source=settings.camera_source,
            warmup_frames=settings.camera_warmup_frames,
            buffer_size=settings.camera_buffer_size,
        )

        try:
            camera_manager.start()
        except CameraInitializationError as exc:
            logger.error(
                "Failed to initialize camera",
                extra={"source": settings.camera_source},
                exc_info=exc,
            )
            raise

        app.state.camera_manager = camera_manager
        app.state.cleanup_task = asyncio.create_task(cleanup_loop(settings))

    @app.on_event("shutdown")
    async def shutdown_services() -> None:
        """Stop the cleanup loop and release the camera."""
        cleanup_task = getattr(app.state, "cleanup_task", None)
        if cleanup_task:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
            app.state.cleanup_task = None

        camera_manager = getattr(app.state, "camera_manager", None)
        if camera_manager:
            camera_manager.stop()
            app.state.camera_manager = None

    return app


app = create_app()


