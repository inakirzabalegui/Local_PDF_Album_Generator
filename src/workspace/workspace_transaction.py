"""Atomic transaction primitive for workspace mutations.

Wraps a multi-step mutation in CoW snapshot + automatic rollback on exception.
Built on top of the snapshot mechanism originally added inline in apply_sync
(C1 fix). Now reusable: any caller wanting all-or-nothing semantics on a
workspace mutation can wrap its code in ``with workspace_transaction(ws):``.

Implementation
--------------
- On macOS APFS: ``cp -c -R`` produces an instant copy-on-write clone — the
  snapshot is effectively free in space and time until the original is
  modified.
- On other platforms: falls back to ``shutil.copytree`` (full copy).
- Rollback = rmtree the (partially-mutated) workspace, then ``os.rename``
  the snapshot back into place (atomic same-filesystem rename).
- If snapshot creation fails, the block runs UNPROTECTED with a logged
  warning — callers don't have to handle "snapshot impossible" specially;
  they just lose the atomicity guarantee for that call.

Usage
-----
    from src.workspace.workspace_transaction import workspace_transaction

    with workspace_transaction(workspace):
        write_page_configs(pages)
        for f in files_to_delete:
            f.unlink()
        # Any exception here → rmtree(workspace), restore snapshot, re-raise.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger("album.workspace.transaction")

_SNAPSHOT_SUFFIX = ".sync_snapshot"


def _create_workspace_snapshot(workspace: Path) -> Path | None:
    """Create a sibling snapshot of the workspace for rollback on failure.

    Uses APFS clonefile on Darwin (`cp -c -R`) — instant copy-on-write, no real
    data duplication until the original is modified. Falls back to
    ``shutil.copytree`` on other platforms. Returns the snapshot path, or
    None if snapshotting failed (caller should proceed without rollback).
    """
    snapshot = workspace.with_name(workspace.name + _SNAPSHOT_SUFFIX)
    # Clean any stale snapshot from a prior crash.
    if snapshot.exists():
        try:
            shutil.rmtree(snapshot)
        except Exception as e:
            logger.warning("Could not remove stale snapshot %s: %s", snapshot, e)
            return None

    if sys.platform == "darwin":
        try:
            subprocess.run(
                ["cp", "-c", "-R", str(workspace), str(snapshot)],
                check=True, capture_output=True,
            )
            return snapshot
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.info("APFS clone unavailable (%s); falling back to copytree", e)

    try:
        shutil.copytree(workspace, snapshot, symlinks=True)
        return snapshot
    except Exception as e:
        logger.error("Failed to create workspace snapshot: %s", e)
        return None


def _restore_workspace_from_snapshot(workspace: Path, snapshot: Path) -> bool:
    """rmtree the (partially-mutated) workspace, then rename snapshot back."""
    try:
        if workspace.exists():
            shutil.rmtree(workspace)
        os.rename(snapshot, workspace)
        return True
    except Exception as e:
        logger.error("Failed to restore workspace from snapshot %s: %s", snapshot, e)
        return False


def _discard_workspace_snapshot(snapshot: Path) -> None:
    """Best-effort cleanup of the snapshot after a successful operation."""
    try:
        if snapshot.exists():
            shutil.rmtree(snapshot)
    except Exception as e:
        logger.warning("Could not remove snapshot %s: %s", snapshot, e)


@contextmanager
def workspace_transaction(workspace: Path) -> Iterator[None]:
    """Run a block under workspace atomicity (snapshot + auto-rollback).

    On exception inside the block: the workspace is restored from snapshot
    and the exception re-raised. On normal exit: the snapshot is discarded.
    On snapshot-creation failure: the block runs unprotected with a logged
    warning (better to make a non-atomic best-effort attempt than to refuse
    the entire operation).
    """
    snapshot = _create_workspace_snapshot(workspace)
    if snapshot is None:
        logger.warning(
            "workspace_transaction: snapshot creation failed for %s; "
            "running block WITHOUT rollback safety", workspace,
        )
        yield
        return

    try:
        yield
    except Exception:
        logger.warning(
            "workspace_transaction: block raised; rolling back %s from snapshot",
            workspace,
        )
        _restore_workspace_from_snapshot(workspace, snapshot)
        raise

    _discard_workspace_snapshot(snapshot)
