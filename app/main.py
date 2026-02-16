"""FastAPI application factory for the camera service."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
import inspect
from typing import Sequence

from fastapi import FastAPI

from .api import router
from .camera import (
    CameraInitializationError,
    CameraManager,
    normalize_camera_source,
    parse_extra_camera_sources,
    source_equivalence_keys,
)
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


def _build_camera_manager(settings: Settings, source: str) -> CameraManager:
    """Build a CameraManager instance for a specific source token."""
    device_index = int(source) if source.isdigit() else 0
    return CameraManager(
        device_index=device_index,
        source=source,
        warmup_frames=settings.camera_warmup_frames,
        buffer_size=settings.camera_buffer_size,
    )


def _validate_main_extra_duplicates(main_source: str, extra_sources: Sequence[str]) -> None:
    """Fail fast if any extra source resolves to the same camera as main."""
    main_keys = source_equivalence_keys(main_source)
    main_normalized = normalize_camera_source(main_source)
    for extra_source in extra_sources:
        extra_keys = source_equivalence_keys(extra_source)
        if main_keys.intersection(extra_keys):
            logger.error(
                "Extra camera source duplicates main camera source",
                extra={
                    "main_source": main_source,
                    "main_normalized": main_normalized,
                    "extra_source": extra_source,
                    "extra_normalized": normalize_camera_source(extra_source),
                },
            )
            raise SystemExit(1)


def initialize_camera_managers(settings: Settings) -> tuple[CameraManager, list[CameraManager]]:
    """
    Initialize the main camera manager and any extra managers.

    Main camera failures are fatal, while extra camera failures are warnings only.
    """
    main_source = settings.main_camera_source or ""
    extra_sources = parse_extra_camera_sources(settings.extra_camera_sources)

    if settings.used_deprecated_camera_source:
        logger.warning(
            "CAMERA_SOURCE is deprecated; use MAIN_CAMERA_SOURCE instead.",
            extra={"deprecated_source": settings.deprecated_camera_source},
        )

    logger.info(
        "Resolved camera sources",
        extra={
            "main_source": main_source,
            "main_normalized": normalize_camera_source(main_source),
            "configured_extra_count": len(extra_sources),
        },
    )

    _validate_main_extra_duplicates(main_source, extra_sources)

    main_manager = _build_camera_manager(settings, main_source)
    try:
        main_manager.start()
    except CameraInitializationError as exc:
        logger.error(
            "Failed to initialize main camera source",
            extra={
                "source": main_source,
                "normalized_source": normalize_camera_source(main_source),
            },
            exc_info=exc,
        )
        raise SystemExit(1) from exc

    extra_managers: list[CameraManager] = []
    for extra_source in extra_sources:
        extra_manager = _build_camera_manager(settings, extra_source)
        try:
            extra_manager.start()
        except CameraInitializationError as exc:
            logger.warning(
                "Failed to initialize extra camera source; ignoring source.",
                extra={
                    "source": extra_source,
                    "normalized_source": normalize_camera_source(extra_source),
                },
                exc_info=exc,
            )
            continue
        extra_managers.append(extra_manager)

    logger.info(
        "Camera initialization complete",
        extra={
            "main_source": main_source,
            "active_extra_count": len(extra_managers),
            "configured_extra_count": len(extra_sources),
        },
    )
    return main_manager, extra_managers


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
    app.state.extra_camera_managers = []
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
        camera_manager, extra_camera_managers = initialize_camera_managers(settings)
        app.state.camera_manager = camera_manager
        app.state.extra_camera_managers = extra_camera_managers
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

        extra_camera_managers = getattr(app.state, "extra_camera_managers", [])
        for extra_camera_manager in extra_camera_managers:
            extra_camera_manager.stop()
        app.state.extra_camera_managers = []

    return app


app = create_app()


