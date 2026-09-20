"""Safe README.md rendering for generated detail pages."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

from .models import CatalogWarning
from .scanner import MEDIA_EXTENSIONS


_MARKDOWN = MarkdownIt("commonmark", {"html": False})
_ALLOWED_LOCAL_EXTENSIONS = {
    extension for extensions in MEDIA_EXTENSIONS.values() for extension in extensions
}


def _tokens(tokens: Iterable[Token]) -> Iterable[Token]:
    for token in tokens:
        yield token
        if token.children:
            yield from _tokens(token.children)


def _inside(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _rewrite_local_url(
    value: str,
    source_directory: Path,
    boundary: Path,
    page: Path,
    image: bool,
) -> Optional[str]:
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https", "mailto"} or parsed.netloc:
        return value
    if parsed.scheme or value.startswith("//"):
        return None
    if not parsed.path:
        return value if parsed.fragment else None

    candidate = (source_directory / unquote(parsed.path)).resolve(strict=False)
    if not _inside(boundary.resolve(), candidate) or not candidate.is_file():
        return None
    extension = candidate.suffix.casefold()
    if extension not in _ALLOWED_LOCAL_EXTENSIONS:
        return None
    if image and extension not in MEDIA_EXTENSIONS["image"]:
        return None

    relative = os.path.relpath(candidate, start=page.parent)
    encoded_path = quote(relative.replace(os.sep, "/"), safe="/")
    return urlunsplit(("", "", encoded_path, parsed.query, parsed.fragment))


def render_readme(
    readme: Optional[Path],
    boundary: Path,
    page: Path,
    warnings: List[CatalogWarning],
) -> str:
    if readme is None:
        return ""
    try:
        source = readme.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        warnings.append(
            CatalogWarning("unreadable-readme", f"Could not read {readme}: {error}")
        )
        return ""

    parsed = _MARKDOWN.parse(source)
    for token in _tokens(parsed):
        if token.type not in {"link_open", "image"}:
            continue
        attribute = "src" if token.type == "image" else "href"
        value = token.attrGet(attribute)
        if value is None:
            continue
        rewritten = _rewrite_local_url(
            value,
            readme.parent,
            boundary,
            page,
            image=token.type == "image",
        )
        token.attrSet(attribute, rewritten or "#")
        if token.type == "link_open" and rewritten and urlsplit(rewritten).scheme:
            token.attrSet("rel", "noopener noreferrer")

    return _MARKDOWN.renderer.render(parsed, _MARKDOWN.options, {})
