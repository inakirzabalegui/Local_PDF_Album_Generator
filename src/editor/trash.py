"""Reversible trash for editor deletions.

Files and folders are moved under `<root>/.trash/<timestamp>_<uuid>/` instead of
being unlinked, so the frontend undo stack can restore them. The trash survives
server restarts; it is emptied only when the user opens a different source
folder (see api_bootstrap).
"""

from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("album.editor.trash")

TRASH_DIR_NAME = ".trash"
ENTRY_META = "entry.meta"
ENTRY_PAYLOAD_META = "payload.meta.json"


@dataclass(frozen=True)
class TrashToken:
    """Handle returned when something is moved to the trash.

    token_id identifies the trash entry; origin_rel is the original path
    relative to the trash root, used to restore it. payload_meta carries
    optional restore hints (manifest entry, tombstone key, etc.) — see
    move_to_trash.
    """
    token_id: str
    origin_rel: str
    payload_meta: dict[str, Any] = field(default_factory=dict)


def _trash_root(root: Path) -> Path:
    return root / TRASH_DIR_NAME


def _ensure_trash(root: Path) -> Path:
    trash = _trash_root(root)
    trash.mkdir(parents=True, exist_ok=True)
    return trash


def _new_entry_dir(trash: Path) -> tuple[str, Path]:
    token_id = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    entry = trash / token_id
    entry.mkdir(parents=True, exist_ok=False)
    return token_id, entry


def move_to_trash(
    root: Path,
    target: Path,
    payload_meta: dict[str, Any] | None = None,
) -> TrashToken:
    """Move `target` (file or folder) into `<root>/.trash/<token>/`.

    `target` must live under `root`. Optional `payload_meta` is persisted next
    to the trashed payload and returned on restore — callers use it to rebuild
    side-state (manifests, tombstones, etc.). Returns a token usable by
    restore_from_trash.
    """
    root = root.resolve()
    target = target.resolve()
    try:
        origin_rel = target.relative_to(root)
    except ValueError as e:
        raise ValueError(f"Target {target} is not inside {root}") from e

    if not target.exists():
        raise FileNotFoundError(f"Target does not exist: {target}")

    trash = _ensure_trash(root)
    token_id, entry = _new_entry_dir(trash)

    destination = entry / target.name
    shutil.move(str(target), str(destination))

    meta = entry / ENTRY_META
    meta.write_text(str(origin_rel), encoding="utf-8")

    meta_obj = dict(payload_meta or {})
    if meta_obj:
        try:
            (entry / ENTRY_PAYLOAD_META).write_text(
                json.dumps(meta_obj, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Failed to write payload meta for {token_id}: {e}")

    logger.info(f"Trashed {origin_rel} → {token_id}")
    return TrashToken(
        token_id=token_id,
        origin_rel=str(origin_rel),
        payload_meta=meta_obj,
    )


def read_payload_meta(root: Path, token_id: str) -> dict[str, Any]:
    """Return the payload metadata stored alongside a trash entry, if any."""
    entry = _trash_root(root.resolve()) / token_id
    meta_path = entry / ENTRY_PAYLOAD_META
    if not meta_path.is_file():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Failed reading payload meta for {token_id}: {e}")
        return {}


def restore_from_trash(root: Path, token_id: str) -> tuple[Path, dict[str, Any]]:
    """Restore the entry identified by `token_id` to its original location.

    Returns (restored_path, payload_meta). `payload_meta` is the dict that was
    passed to move_to_trash (or {} if none). Raises if the token is unknown
    or if the destination already exists (caller conflict — e.g. user recreated
    the file manually).
    """
    root = root.resolve()
    trash = _trash_root(root)
    entry = trash / token_id
    if not entry.is_dir():
        raise FileNotFoundError(f"Unknown trash token: {token_id}")

    meta = entry / ENTRY_META
    if not meta.is_file():
        raise FileNotFoundError(f"Trash entry missing metadata: {token_id}")
    origin_rel = meta.read_text(encoding="utf-8").strip()

    payload_meta_path = entry / ENTRY_PAYLOAD_META
    payload_meta: dict[str, Any] = {}
    if payload_meta_path.is_file():
        try:
            payload_meta = json.loads(payload_meta_path.read_text(encoding="utf-8"))
        except Exception:
            payload_meta = {}

    sidecars = {ENTRY_META, ENTRY_PAYLOAD_META}
    payloads = [p for p in entry.iterdir() if p.name not in sidecars]
    if len(payloads) != 1:
        raise RuntimeError(
            f"Malformed trash entry {token_id}: expected 1 payload, found {len(payloads)}"
        )
    payload = payloads[0]

    destination = root / origin_rel
    if destination.exists():
        raise FileExistsError(
            f"Cannot restore {origin_rel}: path already exists"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(payload), str(destination))
    # remove the now-empty entry
    try:
        meta.unlink()
        if payload_meta_path.exists():
            payload_meta_path.unlink()
        entry.rmdir()
    except OSError:
        logger.warning(f"Could not clean up trash entry {token_id}")

    logger.info(f"Restored {origin_rel} from {token_id}")
    return destination, payload_meta


def empty_trash(root: Path) -> int:
    """Delete everything under `<root>/.trash/` permanently.

    Returns the number of entries removed. Missing trash is a no-op.
    """
    trash = _trash_root(root)
    if not trash.is_dir():
        return 0

    count = 0
    for entry in trash.iterdir():
        try:
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            count += 1
        except Exception as e:
            logger.error(f"Failed to empty trash entry {entry}: {e}")

    logger.info(f"Emptied trash at {trash}: {count} entries removed")
    return count
