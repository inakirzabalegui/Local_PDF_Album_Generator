"""Atomic YAML writes for workspace state files.

Single seam for "write a workspace YAML safely". Replaces hand-rolled
write-and-pray patterns scattered across config.py / manifest.py / syncer.py.

Guarantees
----------
- **Atomic on success**: a reader concurrent with the write sees either the
  old content or the new content, never a half-written file. Implemented via
  tempfile-in-same-dir + os.replace.
- **Crash-safe**: if the process dies mid-write, the destination is unchanged
  (the .tmp file may linger and gets overwritten on the next attempt).
- **Unicode-safe**: dumps with allow_unicode=True; ASCII-only escaping is the
  caller's job if they need it.

Two surfaces:
- ``write(path, data, **dump_opts)`` — for data structures that round-trip
  cleanly through ``yaml.safe_dump`` (dicts, lists, scalars).
- ``write_text(path, content)`` — for pre-rendered YAML strings (templates).
  Same atomicity guarantee; no parsing.

Both raise the underlying OSError if the write itself fails — callers should
treat that as a hard error, not a silent skip.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("album.workspace.atomic_yaml")

_TMP_SUFFIX = ".tmp"


def _tmp_for(path: Path) -> Path:
    """Sibling tempfile path; staying on the same filesystem keeps os.replace atomic."""
    return path.with_suffix(path.suffix + _TMP_SUFFIX)


def write(path: Path, data: Any, *, sort_keys: bool = False, allow_unicode: bool = True) -> Path:
    """Serialize ``data`` to YAML and write atomically to ``path``.

    Returns the path on success. Raises OSError on filesystem failure.
    """
    tmp = _tmp_for(path)
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=sort_keys, allow_unicode=allow_unicode)
    os.replace(tmp, path)
    return path


def write_text(path: Path, content: str) -> Path:
    """Write a pre-rendered YAML string atomically to ``path``.

    Use this when the caller produced YAML via a template (avoids re-parsing).
    The content is written verbatim with utf-8 encoding.
    """
    tmp = _tmp_for(path)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)
    return path
