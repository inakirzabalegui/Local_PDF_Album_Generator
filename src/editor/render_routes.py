"""HTTP routes for rendering the album PDF from the web UI."""

from __future__ import annotations

import json
import logging
import queue
import threading
from pathlib import Path

from flask import Response, current_app, jsonify, request, send_file, stream_with_context

from src.editor.app import app

logger = logging.getLogger("album.editor.render")

_render_lock = threading.Lock()
_render_running = False


def _is_render_running() -> bool:
    return _render_running


@app.route('/api/render/album/stream', methods=['POST'])
def api_render_album_stream():
    """Render the album PDF (interior + cover) with SSE progress."""
    global _render_running

    workspace = current_app.config.get('WORKSPACE')
    if not workspace:
        return jsonify({'success': False, 'error': 'No workspace configured'}), 400
    workspace = Path(workspace)
    if not (workspace / 'global_config.yaml').exists():
        return jsonify({'success': False, 'error': 'Workspace sin global_config.yaml'}), 400

    if not _render_lock.acquire(blocking=False):
        return jsonify({'success': False, 'error': 'Render ya en curso'}), 409
    _render_running = True

    progress_queue: queue.Queue = queue.Queue()

    def _run():
        try:
            from src.render.pdf_generator import generate_album
            from src.workspace.config import read_global_config, read_page_configs
            from src.workspace.reconciler import reconcile
            from src.workspace.rebalancer import rebalance

            progress_queue.put({'step': 'reading'})
            global_cfg = read_global_config(workspace)
            pages = read_page_configs(workspace, global_cfg)

            progress_queue.put({'step': 'reconciling'})
            pages = reconcile(pages, global_cfg, workspace)

            progress_queue.put({'step': 'rebalancing'})
            pages = rebalance(pages, global_cfg, workspace)

            progress_queue.put({'step': 'rendering', 'total': len(pages)})

            output_paths = generate_album(pages, global_cfg, workspace)

            outputs = []
            for p in output_paths:
                pp = Path(p)
                outputs.append({
                    'name': pp.name,
                    'path': str(pp),
                    'is_cover': '_cover' in pp.stem.lower(),
                })
            progress_queue.put({'step': 'done', 'outputs': outputs})
        except Exception as e:
            logger.exception('render failed')
            progress_queue.put({'step': 'error', 'message': str(e)})
        finally:
            global _render_running
            _render_running = False
            _render_lock.release()

    threading.Thread(target=_run, daemon=True).start()

    def _generate():
        while True:
            try:
                event = progress_queue.get(timeout=1800)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get('step') in ('done', 'error'):
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'step': 'error', 'message': 'Timeout'})}\n\n"
                break

    return Response(
        stream_with_context(_generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/api/render/output', methods=['GET'])
def api_render_output():
    """Serve a generated PDF from the workspace by basename."""
    workspace = current_app.config.get('WORKSPACE')
    if not workspace:
        return jsonify({'success': False, 'error': 'No workspace configured'}), 400
    workspace = Path(workspace)

    name = request.args.get('name', '')
    if not name or '/' in name or '\\' in name or not name.lower().endswith('.pdf'):
        return jsonify({'success': False, 'error': 'Nombre inválido'}), 400

    target = (workspace / name).resolve()
    try:
        target.relative_to(workspace.resolve())
    except ValueError:
        return jsonify({'success': False, 'error': 'Ruta fuera del workspace'}), 400

    if not target.exists():
        return jsonify({'success': False, 'error': 'PDF no encontrado'}), 404

    return send_file(str(target), mimetype='application/pdf', as_attachment=False)
