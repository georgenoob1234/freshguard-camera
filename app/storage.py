"""Utilities for persisting and retrieving image files."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from fastapi import HTTPException, status
from PIL import Image


class ImageStorage:
    """File-system backed image storage."""

    _jpeg_suffixes: Final[tuple[str, ...]] = (".jpg", ".jpeg")

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _build_path(self, image_id: str, image_format: str) -> Path:
        extension = "jpg" if image_format == "jpeg" else "png"
        return self.base_dir / f"{image_id}.{extension}"

    def save_image(self, image: Image.Image, image_id: str, image_format: str, quality: int) -> Path:
        """Persist the provided image to disk."""
        file_path = self._build_path(image_id, image_format)
        save_kwargs = {"format": image_format.upper()}
        if image_format == "jpeg":
            save_kwargs["quality"] = quality
            save_kwargs["optimize"] = True

        image.save(file_path, **save_kwargs)
        return file_path

    def resolve_image_path(self, filename: str) -> Path:
        """
        Resolve filename within the storage directory, preventing path traversal.

        Raises HTTPException with 404 if the file does not exist.
        """
        candidate = (self.base_dir / filename).resolve()

        try:
            candidate.relative_to(self.base_dir.resolve())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid image path supplied.",
            ) from exc

        if not candidate.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Image not found.",
            )

        return candidate

    @staticmethod
    def guess_media_type(file_path: Path) -> str:
        """Infer MIME type based on file suffix."""
        suffix = file_path.suffix.lower()
        if suffix in ImageStorage._jpeg_suffixes:
            return "image/jpeg"
        if suffix == ".png":
            return "image/png"
        return "application/octet-stream"




