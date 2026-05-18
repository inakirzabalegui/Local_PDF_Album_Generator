"""SSE response helper for long-running operations.

Replaces hand-rolled queue + thread + generator + format triples scattered
across render_routes.py and source_routes.py.

The work function receives an ``emit(event_dict)`` callback. Yield ``{'step': 'done', ...}``
or ``{'step': 'error', ...}`` to terminate the stream. Any other steps stream
through as progress events. Exceptions inside the work function are caught and
surfaced as ``{'step': 'error', 'message': str(e)}``.

If the queue is empty for longer than ``timeout_s`` (default 1800), the stream
emits a timeout error and ends. If the work function returns without ever
emitting ``done`` or ``error``, the stream still ends cleanly (the helper
will emit a synthetic ``done`` after the worker thread joins) — this matches
the C5 fallback we added on the frontend.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from typing import Callable

from flask import Response, stream_with_context

logger = logging.getLogger("album.editor.sse")

# Callable signature: work_fn(emit) where emit(event_dict) pushes to the stream.
WorkFn = Callable[[Callable[[dict], None]], None]


def sse_response(work_fn: WorkFn, *, timeout_s: int = 1800) -> Response:
    """Return a Flask Response that streams progress events from ``work_fn``.

    The worker runs on a daemon thread; the route returns immediately and Flask
    serves the SSE stream. If the worker raises, the exception is surfaced as
    an ``error`` event before the stream ends.
    """
    q: queue.Queue = queue.Queue()
    done_sentinel = object()

    def _emit(event: dict) -> None:
        q.put(event)

    def _run():
        try:
            work_fn(_emit)
        except Exception as e:
            logger.exception("sse_stream work failed")
            q.put({'step': 'error', 'message': str(e)})
        finally:
            q.put(done_sentinel)

    threading.Thread(target=_run, daemon=True).start()

    def _generate():
        while True:
            try:
                event = q.get(timeout=timeout_s)
            except queue.Empty:
                yield f"data: {json.dumps({'step': 'error', 'message': 'Timeout'})}\n\n"
                return
            if event is done_sentinel:
                # Worker finished; if it never sent an explicit done, send one
                # so the client doesn't hang waiting for it.
                yield f"data: {json.dumps({'step': 'done'})}\n\n"
                return
            yield f"data: {json.dumps(event)}\n\n"
            if event.get('step') in ('done', 'error'):
                return

    return Response(
        stream_with_context(_generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
