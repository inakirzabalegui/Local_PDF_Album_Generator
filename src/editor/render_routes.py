"""HTTP routes for rendering the album PDF from the web UI."""

from __future__ import annotations

import logging
from pathlib import Path

from flask import current_app, jsonify, request, send_file

from src.editor.app import app
from src.editor.sse_stream import sse_response
from src.editor.workspace_op import workspace_op, WorkspaceOpBusy

logger = logging.getLogger("album.editor.render")


@app.route('/api/render/album/stream', methods=['POST'])
def api_render_album_stream():
    """Render the album PDF (interior + cover) with SSE progress."""
    workspace = current_app.config.get('WORKSPACE')
    if not workspace:
        return jsonify({'success': False, 'error': 'No workspace configured'}), 400
    workspace = Path(workspace)
    if not (workspace / 'global_config.yaml').exists():
        return jsonify({'success': False, 'error': 'Workspace sin global_config.yaml'}), 400

    # Acquire the global workspace mutex synchronously so we can 409 before
    # opening the SSE stream, not emit an error event into it.
    try:
        _op_cm = workspace_op("render")
        _op_cm.__enter__()
    except WorkspaceOpBusy as busy:
        return jsonify({'success': False, 'error': str(busy)}), 409

    def _work(emit):
        try:
            from src.render.pdf_generator import generate_album
            from src.workspace.config import read_global_config, read_page_configs
            from src.workspace.reconciler import reconcile
            from src.workspace.rebalancer import rebalance

            emit({'step': 'reading'})
            global_cfg = read_global_config(workspace)
            pages = read_page_configs(workspace, global_cfg)

            emit({'step': 'reconciling'})
            pages = reconcile(pages, global_cfg, workspace)

            emit({'step': 'rebalancing'})
            pages = rebalance(pages, global_cfg, workspace)

            emit({'step': 'rendering', 'total': len(pages)})

            output_paths = generate_album(pages, global_cfg, workspace)

            outputs = []
            for p in output_paths:
                pp = Path(p)
                outputs.append({
                    'name': pp.name,
                    'path': str(pp),
                    'is_cover': '_cover' in pp.stem.lower(),
                })
            emit({'step': 'done', 'outputs': outputs})
        finally:
            _op_cm.__exit__(None, None, None)

    return sse_response(_work, timeout_s=1800)


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
