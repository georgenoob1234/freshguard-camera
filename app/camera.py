"""Camera utilities and CameraManager implementation."""

from __future__ import annotations

import logging
import random
from threading import Lock
from typing import Set, Tuple

import numpy as np
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def parse_resolution(resolution: str) -> Tuple[int, int]:
    """Parse a resolution string formatted as '<width>x<height>'."""
    if not resolution:
        raise ValueError("Resolution value is required.")

    parts = resolution.lower().split("x")
    if len(parts) != 2:
        raise ValueError("Resolution must be formatted as '<width>x<height>'.")

    try:
        width, height = (int(parts[0]), int(parts[1]))
    except ValueError as exc:
        raise ValueError("Resolution dimensions must be integers.") from exc

    if width <= 0 or height <= 0:
        raise ValueError("Resolution dimensions must be positive integers.")

    return width, height


def parse_extra_camera_sources(raw_sources: str | None) -> list[str]:
    """Parse a comma-separated extras string into trimmed source tokens."""
    if not raw_sources:
        return []
    return [token.strip() for token in raw_sources.split(",") if token.strip()]


def normalize_camera_source(source: str) -> str:
    """Normalize source representation for deterministic logging and comparison."""
    token = source.strip()
    token_lower = token.lower()
    if token.isdigit():
        return f"index:{int(token)}"
    if token_lower.startswith("/dev/video"):
        return f"dev:{token_lower}"
    return f"raw:{token}"


def source_equivalence_keys(source: str) -> Set[str]:
    """
    Return keys used for duplicate detection.

    This handles common equivalent notations like "0" and "/dev/video0".
    """
    token = source.strip()
    token_lower = token.lower()
    keys: Set[str] = {normalize_camera_source(token)}

    if token.isdigit():
        index_value = int(token)
        keys.add(f"index:{index_value}")
        keys.add(f"dev:/dev/video{index_value}")
        return keys

    if token_lower.startswith("/dev/video"):
        suffix = token_lower[len("/dev/video") :]
        if suffix.isdigit():
            index_value = int(suffix)
            keys.add(f"index:{index_value}")
            keys.add(f"dev:/dev/video{index_value}")

    return keys


class CameraError(RuntimeError):
    """Base exception for camera related failures."""


class CameraInitializationError(CameraError):
    """Raised when the camera device cannot be initialized."""


class CameraCaptureError(CameraError):
    """Raised when the camera fails to provide a fresh frame."""


class CameraManager:
    """Deterministic controller for a single camera device."""

    _dummy_sources = {"", "dummy", "simulator", "placeholder"}

    def __init__(
        self,
        device_index: int = 0,
        *,
        source: str | None = None,
        warmup_frames: int = 3,
        buffer_size: int | None = 1,
    ) -> None:
        self.device_index = device_index
        self.source = (source or str(device_index)).strip()
        self.warmup_frames = max(0, warmup_frames)
        self.buffer_size = buffer_size if buffer_size and buffer_size > 0 else None
        self._lock = Lock()
        self._capture = None
        self._dummy_mode = self._is_dummy_source(self.source)
        self._started = False

    def start(self) -> None:
        """Open the camera device, configure it, and verify it works."""
        with self._lock:
            if self._started:
                return

            if self._dummy_mode:
                logger.info(
                    "Camera manager operating in dummy mode; skipping hardware init.",
                    extra={"source": self.source},
                )
                self._started = True
                return

            try:
                import cv2
            except ImportError as exc:  # pragma: no cover - enforced by requirements
                raise CameraInitializationError("OpenCV is required to open the camera.") from exc

            capture_source = self._resolve_capture_source()
            logger.info("Opening camera device", extra={"source": capture_source})
            capture = cv2.VideoCapture(capture_source)
            if not capture.isOpened():
                capture.release()
                raise CameraInitializationError(f"Unable to open camera source '{self.source}'.")

            if self.buffer_size is not None:
                success = capture.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)
                if not success:
                    logger.warning(
                        "Unable to set camera buffer size",
                        extra={"buffer_size": self.buffer_size},
                    )

            self._capture = capture
            self._started = True
            logger.info("Camera device ready", extra={"source": capture_source})

    def stop(self) -> None:
        """Release the camera device cleanly."""
        with self._lock:
            if self._capture is not None:
                logger.info("Releasing camera source %s", self.source)
                self._capture.release()
                self._capture = None
            self._started = False

    def capture_fresh_frame(
        self,
        resolution: Tuple[int, int],
        format: str,
        quality: int,
    ) -> np.ndarray:
        """Return a fresh frame from the camera."""
        width, height = resolution

        with self._lock:
            if not self._started:
                raise CameraCaptureError("Camera has not been started.")

            if self._dummy_mode:
                return self._generate_dummy_frame(width, height)

            capture = self._capture
            if capture is None:
                raise CameraCaptureError("Camera capture device is unavailable.")

            try:
                import cv2
            except ImportError as exc:  # pragma: no cover - enforced by requirements
                raise CameraCaptureError("OpenCV is required to read from the camera.") from exc

            if self.warmup_frames > 0:
                for _ in range(self.warmup_frames):
                    capture.read()

            success, frame = capture.read()

            if not success or frame is None:
                raise CameraCaptureError("Failed to read frame from camera.")

            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return frame_rgb

    def _resolve_capture_source(self) -> int | str:
        """Interpret the configured source into an OpenCV-compatible value."""
        if self.source.isdigit():
            return int(self.source)
        return self.source

    @classmethod
    def _is_dummy_source(cls, source: str) -> bool:
        return source.strip().lower() in cls._dummy_sources

    @staticmethod
    def _generate_dummy_frame(width: int, height: int) -> np.ndarray:
        image = _generate_placeholder_image(width, height)
        return np.array(image)


def _generate_placeholder_image(width: int, height: int) -> Image.Image:
    """Produce a placeholder gradient image for demonstration."""
    base_color = tuple(random.randint(64, 192) for _ in range(3))
    image = Image.new("RGB", (width, height), base_color)
    draw = ImageDraw.Draw(image)

    draw.line((0, 0, width, height), fill="white", width=max(1, width // 80))
    draw.line((0, height, width, 0), fill="white", width=max(1, width // 80))

    text = f"{width}x{height}"
    text_position = (width // 10, height // 10)
    draw.text(text_position, text, fill="black")
    return image

