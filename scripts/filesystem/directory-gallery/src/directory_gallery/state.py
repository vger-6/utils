"""SQLite-backed incremental catalog and output ownership state."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from . import __version__
from .errors import UserError
from .models import CatalogWarning
from .output import (
    DATABASE_NAME,
    MANIFEST_FORMAT,
    MANIFEST_GENERATOR,
    MANIFEST_NAME,
    write_text_atomic,
)


SCHEMA_VERSION = 1
GENERATED_FILE = re.compile(
    r"^(?:index\.html|creators\.html|projects\.html|"
    r"assets/directory-gallery\.(?:css|js)|"
    r"(?:creators|projects)/[0-9a-f]{16}\.html)$"
)


class CatalogState:
    """Persistent state that remains bounded in memory as the catalog grows."""

    def __init__(
        self,
        output: Path,
        input_root: Path,
        warnings: List[CatalogWarning],
    ) -> None:
        self.output = output
        self.input_root = input_root
        self.warnings = warnings
        self.manifest_path = output / MANIFEST_NAME
        self.database_path = output / DATABASE_NAME
        if os.path.lexists(os.fspath(self.database_path)) and (
            self.database_path.is_symlink() or not self.database_path.is_file()
        ):
            raise UserError(
                "output has an invalid Directory Gallery cache database"
            )
        try:
            self.connection = sqlite3.connect(self.database_path)
        except sqlite3.Error as error:
            raise UserError(
                f"could not open Directory Gallery cache database: {error}"
            ) from error
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute("PRAGMA journal_mode = DELETE")
            self.connection.execute("PRAGMA synchronous = NORMAL")
            self._create_schema()
            self.run_id = self._next_run_id()
            self._mutations = 0
            if not self.manifest_path.exists():
                self._write_manifest()
        except (sqlite3.Error, ValueError) as error:
            self.connection.close()
            raise UserError(
                f"output has an invalid Directory Gallery cache database: {error}"
            ) from error

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS previews (
                source_key TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                file TEXT NOT NULL UNIQUE,
                mtime_ns INTEGER NOT NULL,
                size INTEGER NOT NULL,
                last_seen INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS generated_files (
                path TEXT PRIMARY KEY,
                last_seen INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS creators (
                source_path TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                page TEXT NOT NULL,
                portrait TEXT,
                project_count INTEGER NOT NULL,
                last_seen INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                source_path TEXT PRIMARY KEY,
                creator_path TEXT NOT NULL,
                creator_name TEXT NOT NULL,
                name TEXT NOT NULL,
                page TEXT NOT NULL,
                cover TEXT,
                last_seen INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS creators_seen_name
                ON creators(last_seen, name COLLATE NOCASE, name);
            CREATE INDEX IF NOT EXISTS projects_seen_name
                ON projects(last_seen, name COLLATE NOCASE, name);
            CREATE INDEX IF NOT EXISTS projects_seen_creator_name
                ON projects(
                    last_seen,
                    creator_path,
                    name COLLATE NOCASE,
                    name
                );
            """
        )
        stored = self.connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        if stored is not None and int(stored["value"]) != SCHEMA_VERSION:
            raise UserError("output has an unsupported Directory Gallery cache schema")
        self.connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.connection.commit()

    def _next_run_id(self) -> int:
        row = self.connection.execute(
            "SELECT value FROM metadata WHERE key = 'run_id'"
        ).fetchone()
        run_id = int(row["value"]) + 1 if row else 1
        self.connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES('run_id', ?)",
            (str(run_id),),
        )
        self.connection.commit()
        return run_id

    def _touch(self) -> None:
        self._mutations += 1
        if self._mutations >= 1000:
            self.connection.commit()
            self._mutations = 0

    def preview(self, source_key: str) -> Optional[sqlite3.Row]:
        return self.connection.execute(
            "SELECT kind, file, mtime_ns, size FROM previews WHERE source_key = ?",
            (source_key,),
        ).fetchone()

    def record_preview(
        self,
        source_key: str,
        kind: str,
        filename: str,
        mtime_ns: int,
        size: int,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO previews(source_key, kind, file, mtime_ns, size, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_key) DO UPDATE SET
                kind = excluded.kind,
                file = excluded.file,
                mtime_ns = excluded.mtime_ns,
                size = excluded.size,
                last_seen = excluded.last_seen
            """,
            (source_key, kind, filename, mtime_ns, size, self.run_id),
        )
        self._touch()

    def record_generated(self, filename: str) -> None:
        if not GENERATED_FILE.fullmatch(filename):
            raise ValueError(f"unsafe generated path: {filename}")
        self.connection.execute(
            """
            INSERT INTO generated_files(path, last_seen) VALUES(?, ?)
            ON CONFLICT(path) DO UPDATE SET last_seen = excluded.last_seen
            """,
            (filename, self.run_id),
        )
        self._touch()

    def record_creator(
        self,
        source_path: Path,
        name: str,
        page: str,
        portrait: Optional[str],
        project_count: int,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO creators
                (source_path, name, page, portrait, project_count, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_path) DO UPDATE SET
                name = excluded.name,
                page = excluded.page,
                portrait = excluded.portrait,
                project_count = excluded.project_count,
                last_seen = excluded.last_seen
            """,
            (os.fspath(source_path.resolve()), name, page, portrait, project_count, self.run_id),
        )
        self._touch()

    def record_project(
        self,
        source_path: Path,
        creator_path: Path,
        creator_name: str,
        name: str,
        page: str,
        cover: Optional[str],
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO projects
                (source_path, creator_path, creator_name, name, page, cover, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_path) DO UPDATE SET
                creator_path = excluded.creator_path,
                creator_name = excluded.creator_name,
                name = excluded.name,
                page = excluded.page,
                cover = excluded.cover,
                last_seen = excluded.last_seen
            """,
            (
                os.fspath(source_path.resolve()),
                os.fspath(creator_path.resolve()),
                creator_name,
                name,
                page,
                cover,
                self.run_id,
            ),
        )
        self._touch()

    def creators(self) -> Iterator[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT source_path, name, page, portrait, project_count
            FROM creators WHERE last_seen = ?
            ORDER BY name COLLATE NOCASE, name
            """,
            (self.run_id,),
        )
        yield from cursor

    def projects_for_creator(self, creator_path: str) -> Iterator[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT source_path, name, page, cover
            FROM projects
            WHERE last_seen = ? AND creator_path = ?
            ORDER BY name COLLATE NOCASE, name
            """,
            (self.run_id, creator_path),
        )
        yield from cursor

    def _remove_stale_previews(self) -> None:
        while True:
            rows = self.connection.execute(
                "SELECT source_key, file FROM previews WHERE last_seen != ? LIMIT 500",
                (self.run_id,),
            ).fetchall()
            if not rows:
                break
            for row in rows:
                filename = row["file"]
                if re.fullmatch(
                    r"thumbnails/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{24}\.jpg",
                    filename,
                ):
                    try:
                        target = self.output / filename
                        target.unlink(missing_ok=True)
                        for parent in (target.parent, target.parent.parent):
                            try:
                                parent.rmdir()
                            except OSError:
                                pass
                    except OSError as error:
                        self.warnings.append(
                            CatalogWarning(
                                "stale-preview",
                                f"Could not remove stale preview {filename}: {error}",
                            )
                        )
            self.connection.executemany(
                "DELETE FROM previews WHERE source_key = ?",
                ((row["source_key"],) for row in rows),
            )
            self.connection.commit()

    def _remove_stale_pages(self) -> None:
        while True:
            rows = self.connection.execute(
                "SELECT path FROM generated_files WHERE last_seen != ? LIMIT 500",
                (self.run_id,),
            ).fetchall()
            if not rows:
                break
            for row in rows:
                filename = row["path"]
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
            self.connection.executemany(
                "DELETE FROM generated_files WHERE path = ?",
                ((row["path"],) for row in rows),
            )
            self.connection.commit()

    def _write_manifest(self) -> None:
        manifest: Dict[str, object] = {
            "format": MANIFEST_FORMAT,
            "generator": MANIFEST_GENERATOR,
            "generator_version": __version__,
            "input": os.fspath(self.input_root),
            "database": DATABASE_NAME,
        }
        write_text_atomic(
            self.manifest_path,
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    def finish(self) -> None:
        self.connection.commit()
        self._remove_stale_previews()
        self._remove_stale_pages()
        self.connection.execute(
            "DELETE FROM creators WHERE last_seen != ?", (self.run_id,)
        )
        self.connection.execute(
            "DELETE FROM projects WHERE last_seen != ?", (self.run_id,)
        )
        self.connection.commit()
        self._write_manifest()

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()

    def __enter__(self) -> "CatalogState":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
