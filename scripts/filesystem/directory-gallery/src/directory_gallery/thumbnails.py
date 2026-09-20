"""Incremental, sharded image and PDF preview generation."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

import pymupdf
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import CatalogWarning
from .state import CatalogState


THUMBNAIL_SIZE = (512, 512)


class ThumbnailCache:
    def __init__(
        self,
        output: Path,
        warnings: List[CatalogWarning],
        state: CatalogState,
        progress: Optional[Callable[[], None]] = None,
    ) -> None:
        self.output = output
        self.warnings = warnings
        self.state = state
        self.progress = progress
        self.generated_count = 0
        self.reused_count = 0

    def thumbnail_for(self, source: Path) -> Optional[str]:
        return self._preview_for(source, "image", self._generate_image)

    def pdf_preview_for(self, source: Path) -> Optional[str]:
        return self._preview_for(source, "pdf", self._generate_pdf)

    def _preview_for(self, source: Path, kind: str, generator: object) -> Optional[str]:
        try:
            source_stat = source.stat()
        except OSError as error:
            self._warn_unreadable(source, kind, error)
            return None

        resolved = os.fspath(source.resolve())
        source_key = resolved if kind == "image" else f"{kind}:{resolved}"
        digest = hashlib.sha256(os.fsencode(source_key)).hexdigest()[:24]
        filename = f"{digest}.jpg"
        relative = f"thumbnails/{digest[:2]}/{digest[2:4]}/{filename}"
        target = self.output / relative
        previous = self.state.preview(source_key)

        if (
            previous is not None
            and previous["kind"] == kind
            and previous["file"] == relative
            and previous["mtime_ns"] == source_stat.st_mtime_ns
            and previous["size"] == source_stat.st_size
            and target.is_file()
        ):
            self.state.record_preview(
                source_key,
                kind,
                relative,
                source_stat.st_mtime_ns,
                source_stat.st_size,
            )
            self.reused_count += 1
            if self.progress:
                self.progress()
            return relative

        try:
            generator(source, target)  # type: ignore[operator]
        except (
            OSError,
            RuntimeError,
            ValueError,
            UnidentifiedImageError,
            Image.DecompressionBombError,
        ) as error:
            self._warn_unreadable(source, kind, error)
            if self.progress:
                self.progress()
            return None

        self.state.record_preview(
            source_key,
            kind,
            relative,
            source_stat.st_mtime_ns,
            source_stat.st_size,
        )
        self.generated_count += 1
        if self.progress:
            self.progress()
        return relative

    @staticmethod
    def _temporary_path(target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.stem}.", suffix=".jpg", dir=target.parent
        )
        os.close(descriptor)
        return Path(temporary_name)

    @staticmethod
    def _prepare_image(image: Image.Image) -> Image.Image:
        image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
            rgba = image.convert("RGBA")
            flattened = Image.new("RGB", rgba.size, "#111720")
            flattened.paste(rgba, mask=rgba.getchannel("A"))
            return flattened
        return image.convert("RGB")

    def _save_image(self, image: Image.Image, target: Path) -> None:
        temporary = self._temporary_path(target)
        try:
            prepared = self._prepare_image(image)
            prepared.save(
                temporary,
                format="JPEG",
                quality=85,
                optimize=True,
                progressive=True,
            )
            os.replace(temporary, target)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def _generate_image(self, source: Path, target: Path) -> None:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened)
            self._save_image(image, target)

    def _generate_pdf(self, source: Path, target: Path) -> None:
        with pymupdf.open(source) as document:
            if document.page_count < 1:
                raise ValueError("PDF has no pages")
            page = document.load_page(0)
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            self._save_image(image, target)

    def _warn_unreadable(self, source: Path, kind: str, error: BaseException) -> None:
        label = "PDF preview" if kind == "pdf" else "thumbnail"
        self.warnings.append(
            CatalogWarning(
                "unreadable-preview",
                f"Could not create {label} for {source}: {error}",
            )
        )
