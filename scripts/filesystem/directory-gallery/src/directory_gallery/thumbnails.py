"""Incremental, manifest-backed image and PDF preview generation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

import pymupdf
from PIL import Image, ImageOps, UnidentifiedImageError

from . import __version__
from .models import CatalogWarning
from .output import (
    MANIFEST_FORMAT,
    MANIFEST_GENERATOR,
    MANIFEST_NAME,
    write_text_atomic,
)


THUMBNAIL_SIZE = (512, 512)
THUMBNAIL_NAME = re.compile(r"^[0-9a-f]{24}\.jpg$")
GENERATED_FILE = re.compile(
    r"^(?:index\.html|projects\.html|"
    r"assets/directory-gallery\.(?:css|js)|"
    r"(?:creators|projects)/[0-9a-f]{16}\.html)$"
)


class ThumbnailCache:
    def __init__(self, output: Path, warnings: List[CatalogWarning]) -> None:
        self.output = output
        self.directory = output / "thumbnails"
        self.manifest_path = output / MANIFEST_NAME
        self.warnings = warnings
        self.previous, self.previous_generated = self._load_manifest()
        self.current: MutableMapping[str, Dict[str, object]] = {}

    def _load_manifest(self) -> Tuple[Mapping[str, object], Tuple[str, ...]]:
        if not self.manifest_path.is_file():
            return {}, ()
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or data.get("format") != MANIFEST_FORMAT
                or data.get("generator") != MANIFEST_GENERATOR
            ):
                raise ValueError("unsupported manifest format")
            thumbnails = data.get("thumbnails", {})
            if not isinstance(thumbnails, dict):
                raise ValueError("invalid thumbnail map")
            generated = data.get("generated_files", [])
            if not isinstance(generated, list) or not all(
                isinstance(item, str) for item in generated
            ):
                raise ValueError("invalid generated-file list")
            return thumbnails, tuple(generated)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.warnings.append(
                CatalogWarning(
                    "invalid-manifest",
                    f"Ignoring unreadable thumbnail manifest: {error}",
                )
            )
            return {}, ()

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
        target = self.directory / filename
        record: Dict[str, object] = {
            "file": filename,
            "kind": kind,
            "mtime_ns": source_stat.st_mtime_ns,
            "size": source_stat.st_size,
        }

        previous = self.previous.get(source_key)
        if previous == record and target.is_file():
            self.current[source_key] = record
            return f"thumbnails/{filename}"

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
            return None

        self.current[source_key] = record
        return f"thumbnails/{filename}"

    def _temporary_path(self, target: Path) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.stem}.", suffix=".jpg", dir=self.directory
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

    def finish(self, input_root: Path, generated_files: Iterable[str]) -> None:
        current_files = {
            str(record["file"])
            for record in self.current.values()
            if isinstance(record.get("file"), str)
        }
        previous_files = {
            str(record["file"])
            for record in self.previous.values()
            if isinstance(record, dict) and isinstance(record.get("file"), str)
        }

        for filename in previous_files - current_files:
            if not THUMBNAIL_NAME.fullmatch(filename):
                continue
            try:
                (self.directory / filename).unlink(missing_ok=True)
            except OSError as error:
                self.warnings.append(
                    CatalogWarning(
                        "stale-thumbnail",
                        f"Could not remove stale thumbnail {filename}: {error}",
                    )
                )

        current_generated = set(generated_files)
        for filename in set(self.previous_generated) - current_generated:
            if not GENERATED_FILE.fullmatch(filename):
                continue
            try:
                target = self.output / filename
                target.unlink(missing_ok=True)
                if target.parent.name in {"creators", "projects"}:
                    try:
                        target.parent.rmdir()
                    except OSError:
                        pass
            except OSError as error:
                self.warnings.append(
                    CatalogWarning(
                        "stale-page",
                        f"Could not remove stale generated page {filename}: {error}",
                    )
                )

        manifest = {
            "format": MANIFEST_FORMAT,
            "generator": MANIFEST_GENERATOR,
            "generator_version": __version__,
            "input": os.fspath(input_root),
            "generated_files": sorted(current_generated),
            "thumbnails": dict(sorted(self.current.items())),
        }
        write_text_atomic(
            self.manifest_path,
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
