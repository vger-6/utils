"""Infer optional creator relationships from conventional folder names."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional, Tuple


def collaboration_members(
    name: str, creators_by_name: Mapping[str, Path]
) -> Tuple[Tuple[str, Optional[Path]], ...]:
    """Split ``A & B`` only when at least one distinct member has a folder."""

    if " & " not in name:
        return ()
    names = tuple(part.strip() for part in name.split(" & "))
    if len(names) < 2 or any(not part for part in names) or len(set(names)) != len(names):
        return ()
    members = tuple((part, creators_by_name.get(part)) for part in names)
    return members if any(path is not None for _, path in members) else ()
