"""Unified concurrency primitive for workspace-mutating operations.

Replaces the parallel (_regen_lock, _regen_running) and (_render_lock, _render_running)
patterns with a single named-op context manager. Routes consult ``current_op()``
or ``is_running()`` instead of reaching into another module's internals.

Only ONE workspace op may run at a time across the whole process. Acquire
attempts are non-blocking by default and raise ``WorkspaceOpBusy`` so callers
can return a 409 with the name of the currently-running op.

Usage
-----
    from src.editor.workspace_op import workspace_op, WorkspaceOpBusy

    try:
        with workspace_op("sync"):
            do_work()
    except WorkspaceOpBusy as e:
        return jsonify({"error": str(e)}), 409
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger("album.editor.workspace_op")

_lock = threading.Lock()
_current_op: str | None = None


def current_op() -> str | None:
    """Return the name of the running workspace op, or None if idle."""
    return _current_op


def is_running() -> bool:
    """True if any workspace op is currently in progress."""
    return _current_op is not None


class WorkspaceOpBusy(RuntimeError):
    """Raised when a workspace op cannot acquire the global mutex.

    The ``current`` attribute names the op that holds the lock so callers
    can surface a useful error message.
    """

    def __init__(self, current: str | None):
        self.current = current or "unknown"
        super().__init__(f"workspace busy: {self.current} in progress")


@contextmanager
def workspace_op(name: str, *, blocking: bool = False) -> Iterator[None]:
    """Acquire the global workspace mutex under a named op.

    Args:
        name: short identifier for the op ("sync", "render", "regenerate").
              Used as the value of ``current_op()`` while the block is active
              and embedded in WorkspaceOpBusy messages.
        blocking: if True, wait for the lock; if False (default), raise
              WorkspaceOpBusy immediately when another op is running.

    Raises:
        WorkspaceOpBusy: when blocking=False and another op holds the lock.
    """
    global _current_op
    if not _lock.acquire(blocking=blocking):
        raise WorkspaceOpBusy(_current_op)
    _current_op = name
    logger.info("workspace_op start: %s", name)
    try:
        yield
    finally:
        logger.info("workspace_op end: %s", name)
        _current_op = None
        _lock.release()
