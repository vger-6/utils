"""Incremental, manifest-backed thumbnail generation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Mapping, MutableMapping, Optional

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


class ThumbnailCache:
    def __init__(self, output: Path, warnings: List[CatalogWarning]) -> None:
        self.output = output
        self.directory = output / "thumbnails"
        self.manifest_path = output / MANIFEST_NAME
        self.warnings = warnings
        self.previous: Mapping[str, object] = self._load_manifest()
        self.current: MutableMapping[str, Dict[str, object]] = {}

    def _load_manifest(self) -> Mapping[str, object]:
        if not self.manifest_path.is_file():
            return {}
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
            return thumbnails
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.warnings.append(
                CatalogWarning(
                    "invalid-manifest",
                    f"Ignoring unreadable thumbnail manifest: {error}",
                )
            )
            return {}

    def thumbnail_for(self, source: Path) -> Optional[str]:
        try:
            source_stat = source.stat()
        except OSError as error:
            self._warn_unreadable(source, error)
            return None

        source_key = os.fspath(source.resolve())
        digest = hashlib.sha256(os.fsencode(source_key)).hexdigest()[:24]
        filename = f"{digest}.jpg"
        target = self.directory / filename
        record: Dict[str, object] = {
            "file": filename,
            "mtime_ns": source_stat.st_mtime_ns,
            "size": source_stat.st_size,
        }

        previous = self.previous.get(source_key)
        if previous == record and target.is_file():
            self.current[source_key] = record
            return f"thumbnails/{filename}"

        try:
            self._generate(source, target)
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as error:
            self._warn_unreadable(source, error)
            return None

        self.current[source_key] = record
        return f"thumbnails/{filename}"

    def _generate(self, source: Path, target: Path) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.stem}.", suffix=".jpg", dir=self.directory
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)

        try:
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened)
                image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    flattened = Image.new("RGB", rgba.size, "#111720")
                    flattened.paste(rgba, mask=rgba.getchannel("A"))
                    image = flattened
                else:
                    image = image.convert("RGB")

                image.save(
                    temporary_path,
                    format="JPEG",
                    quality=85,
                    optimize=True,
                    progressive=True,
                )
            os.replace(temporary_path, target)
        except BaseException:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
            raise

    def _warn_unreadable(self, source: Path, error: BaseException) -> None:
        self.warnings.append(
            CatalogWarning(
                "unreadable-image",
                f"Could not create thumbnail for {source}: {error}",
            )
        )

    def finish(self, input_root: Path) -> None:
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

        manifest = {
            "format": MANIFEST_FORMAT,
            "generator": MANIFEST_GENERATOR,
            "generator_version": __version__,
            "input": os.fspath(input_root),
            "thumbnails": dict(sorted(self.current.items())),
        }
        write_text_atomic(
            self.manifest_path,
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
