"""Tombstones for photos intentionally removed in the editor.

When a user deletes a photo or page in Edición mode, the source folder still
contains the underlying file. Without a tombstone, the next `compute_sync_diff`
would treat the deletion as an "added photo" delta and offer to re-import it
on apply.

A tombstone is identified by (section_id, source_path). The pair is stable
across source-folder renames because section_id is persisted to the source
folder's `.album_meta.yaml`. Path-only matching would break when the user
renames the source folder containing the deleted photo.

The store lives at `<workspace>/.deleted_photos.yaml`. It is created on
demand.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger("album.tombstones")

TOMBSTONE_FILE = ".deleted_photos.yaml"


def _path(workspace: Path) -> Path:
    return workspace / TOMBSTONE_FILE


def _load(workspace: Path) -> list[dict]:
    path = _path(workspace)
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to read tombstones at {path}: {e}")
        return []
    items = data.get("tombstones", [])
    if not isinstance(items, list):
        return []
    return [it for it in items if isinstance(it, dict)]


def _save(workspace: Path, items: list[dict]) -> None:
    path = _path(workspace)
    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                {"tombstones": items},
                f,
                sort_keys=False,
                allow_unicode=True,
            )
    except Exception as e:
        logger.error(f"Failed writing tombstones to {path}: {e}")


def read_tombstones(workspace: Path) -> set[tuple[str, str]]:
    """Return the set of (section_id, source_path) tombstones."""
    items = _load(workspace)
    out: set[tuple[str, str]] = set()
    for it in items:
        sid = str(it.get("section_id", "") or "")
        sp = str(it.get("source_path", "") or "")
        if sp:
            out.add((sid, sp))
    return out


def add_tombstone(workspace: Path, section_id: str, source_path: str) -> None:
    """Record that a photo was intentionally removed from the workspace."""
    if not source_path:
        return
    items = _load(workspace)
    key = (section_id or "", source_path)
    if any(
        (str(it.get("section_id", "")), str(it.get("source_path", ""))) == key
        for it in items
    ):
        return
    items.append({"section_id": section_id or "", "source_path": source_path})
    _save(workspace, items)
    logger.info(f"Tombstone added: section={section_id} path={source_path}")


def remove_tombstone(workspace: Path, section_id: str, source_path: str) -> bool:
    """Erase a tombstone (e.g. on undo / restore from trash). Returns True if found."""
    items = _load(workspace)
    before = len(items)
    items = [
        it for it in items
        if not (
            str(it.get("section_id", "")) == (section_id or "")
            and str(it.get("source_path", "")) == source_path
        )
    ]
    if len(items) == before:
        return False
    _save(workspace, items)
    logger.info(f"Tombstone removed: section={section_id} path={source_path}")
    return True


def rewrite_section_paths(
    workspace: Path,
    section_id: str,
    old_prefix: str,
    new_prefix: str,
) -> int:
    """Rewrite the source-folder prefix of tombstones for a renamed section.

    Returns the number of tombstones modified.
    """
    if not section_id or old_prefix == new_prefix:
        return 0
    old_prefix = old_prefix.rstrip("/") + "/"
    new_prefix = new_prefix.rstrip("/") + "/"
    items = _load(workspace)
    changed = 0
    for it in items:
        if str(it.get("section_id", "")) != section_id:
            continue
        sp = str(it.get("source_path", "") or "")
        if sp.startswith(old_prefix):
            it["source_path"] = new_prefix + sp[len(old_prefix):]
            changed += 1
    if changed:
        _save(workspace, items)
        logger.info(
            f"Rewrote {changed} tombstone path(s) for section {section_id}: "
            f"{old_prefix} → {new_prefix}"
        )
    return changed
