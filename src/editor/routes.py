"""API routes for the interactive editor."""

from __future__ import annotations

import logging
import random
from pathlib import Path

import yaml
from flask import jsonify, request, send_file, current_app

from src.editor.app import app
from src.editor.workspace_manager import (
    load_workspace,
    reorder_photos,
    reorder_pages,
    delete_photo,
    delete_page,
    update_page_title,
    update_photo_caption,
    generate_preview,
    get_page_info,
    get_cover_info,
    set_cover_photo,
    move_photos,
    explode_page,
)
from src.editor.trash import restore_from_trash
from src.workspace.config import VALID_IMAGE_EXTENSIONS
from src.workspace.manifest import add_photo_to_manifest
from src.workspace.tombstones import remove_tombstone

logger = logging.getLogger("album.editor")


@app.route('/api/pages', methods=['GET'])
def api_list_pages():
    """List all pages with metadata, including cover and backcover."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        global_cfg, pages = load_workspace(workspace)

        content_pages = [p for p in pages if not p.is_cover and not p.is_backcover]
        content_pages.sort(key=lambda p: p.page_number)

        cover_page = next((p for p in pages if p.is_cover), None)
        backcover_page = next((p for p in pages if p.is_backcover), None)

        def _cover_payload(p):
            if p is None:
                return None
            imgs = p.image_files()
            return {
                'id': p.folder.name,
                'kind': 'cover' if p.is_cover else 'backcover',
                'image': imgs[0].name if imgs else "",
                'completed': bool(p.completed),
            }

        return jsonify({
            'success': True,
            'cover': _cover_payload(cover_page),
            'backcover': _cover_payload(backcover_page),
            'pages': [{
                'id': p.folder.name,
                'number': p.page_number,
                'title': p.section_titles[0] if p.section_titles else f"Page {p.page_number}",
                'subtitle': p.section_titles[1] if len(p.section_titles) > 1 else "",
                'photo_count': p.photo_count,
                'layout_mode': p.layout_mode,
                'completed': p.completed,
                'section_id': p.section_id,
            } for p in content_pages]
        })
    except Exception as e:
        logger.error(f"Failed to list pages: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cover/<kind>', methods=['GET'])
def api_get_cover(kind):
    """Detail for the cover (kind='cover') or backcover (kind='backcover')."""
    if kind not in ('cover', 'backcover'):
        return jsonify({'success': False, 'error': f'Unknown kind: {kind}'}), 400
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        info = get_cover_info(workspace, kind)
        if not info:
            return jsonify({'success': False, 'error': f'{kind} folder not found'}), 404
        return jsonify({'success': True, 'cover': info})
    except Exception as e:
        logger.error(f"Failed to get {kind} info: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cover/<kind>/photo', methods=['POST'])
def api_set_cover_photo(kind):
    """Replace the cover photo with a clone of a workspace page photo.

    Body: {source_page: '<page_folder_name>', source_image: '<img_NNN.jpg>'}.
    The original photo on the source page is left untouched.
    """
    if kind not in ('cover', 'backcover'):
        return jsonify({'success': False, 'error': f'Unknown kind: {kind}'}), 400
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        data = request.get_json() or {}
        source_page = data.get('source_page')
        source_image = data.get('source_image')
        if not source_page or not source_image:
            return jsonify({
                'success': False,
                'error': 'source_page and source_image required',
            }), 400
        result = set_cover_photo(workspace, kind, source_page, source_image)
        status = 200 if result.get('success') else 400
        return jsonify(result), status
    except Exception as e:
        logger.error(f"Failed to set {kind} photo: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sections/resort', methods=['POST'])
def api_resort_sections():
    """Resort all content pages by section date. Body: {} (no params needed)."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        source_root_str = current_app.config.get('SOURCE')
        source_root = Path(source_root_str) if source_root_str else None

        from src.workspace.resort import resort_sections
        result = resort_sections(workspace, source_root=source_root)

        if not result['success']:
            return jsonify(result), 400

        return jsonify(result)

    except Exception as e:
        logger.error(f"Failed to resort sections: {e}")
        return jsonify({'success': False, 'error': str(e), 'renamed_pages': [], 'focus_section_id': None}), 500


@app.route('/api/pages/reorder', methods=['POST'])
def api_reorder_pages():
    """Reorder content pages. Body: {ordered_page_ids: [...]}"""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        data = request.get_json() or {}
        ordered_page_ids = data.get('ordered_page_ids', [])
        moved_page_id = data.get('moved_page_id')  # optional; may be None

        if not ordered_page_ids:
            return jsonify({'success': False, 'error': 'No ordered_page_ids provided'}), 400

        result = reorder_pages(workspace, ordered_page_ids, moved_page_id=moved_page_id)

        if not result['success']:
            return jsonify(result), 400

        return jsonify(result)

    except Exception as e:
        logger.error(f"Failed to reorder pages: {e}")
        return jsonify({'success': False, 'error': str(e), 'renamed_pages': []}), 500


@app.route('/api/page/<page_id>', methods=['GET'])
def api_get_page(page_id):
    """Get specific page details and photos."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        page_folder = workspace / page_id
        
        if not page_folder.exists():
            return jsonify({'success': False, 'error': 'Page not found'}), 404
        
        info = get_page_info(page_folder)
        
        return jsonify({
            'success': True,
            'page': info
        })
    except Exception as e:
        logger.error(f"Failed to get page {page_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/page/<page_id>/reorder', methods=['POST'])
def api_reorder_photos(page_id):
    """Reorder photos in a page."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        page_folder = workspace / page_id
        
        if not page_folder.exists():
            return jsonify({'success': False, 'error': 'Page not found'}), 404
        
        data = request.get_json()
        new_order = data.get('order', [])
        
        if not new_order:
            return jsonify({'success': False, 'error': 'No order provided'}), 400
        
        success = reorder_photos(page_folder, new_order)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to reorder photos'}), 500
            
    except Exception as e:
        logger.error(f"Failed to reorder photos in {page_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/page/<page_id>/move-photos', methods=['POST'])
def api_move_photos(page_id):
    """Move photos from one page to another."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        from_folder = workspace / page_id
        
        if not from_folder.exists():
            return jsonify({'success': False, 'error': 'Source page not found'}), 404
        
        data = request.get_json()
        target_page_id = data.get('target_page_id')
        filenames = data.get('filenames', [])
        
        if not target_page_id or not filenames:
            return jsonify({'success': False, 'error': 'Missing target_page_id or filenames'}), 400
        
        to_folder = workspace / target_page_id
        if not to_folder.exists():
            return jsonify({'success': False, 'error': 'Target page not found'}), 404
        
        success = move_photos(from_folder, to_folder, filenames)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to move photos'}), 500
            
    except Exception as e:
        logger.error(f"Failed to move photos to {page_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/page/<page_id>/delete-photo', methods=['DELETE'])
def api_delete_photo(page_id):
    """Delete a specific photo from a page."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        page_folder = workspace / page_id
        
        if not page_folder.exists():
            return jsonify({'success': False, 'error': 'Page not found'}), 404
        
        data = request.get_json()
        filename = data.get('filename')
        
        if not filename:
            return jsonify({'success': False, 'error': 'No filename provided'}), 400

        # #region agent log
        import json as _json_dbg; open('/Users/jzabalegui/Coding/Local_PDF_Album_Generator/.cursor/debug-02279c.log','a').write(_json_dbg.dumps({"sessionId":"02279c","hypothesisId":"H4","location":"routes.py:api_delete_photo","message":"delete album photo","data":{"page_id":page_id,"filename":filename,"photo_exists":(page_folder/filename).exists(),"workspace":str(workspace)},"timestamp":__import__('time').time()})+'\n')
        # #endregion
        
        token = delete_photo(page_folder, filename, workspace)

        if token is not None:
            return jsonify({
                'success': True,
                'trash_token': token.token_id,
                'trash_scope': 'workspace',
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to delete photo'}), 500

    except Exception as e:
        logger.error(f"Failed to delete photo from {page_id}: {e}")
        # #region agent log
        import json as _json_dbg; open('/Users/jzabalegui/Coding/Local_PDF_Album_Generator/.cursor/debug-02279c.log','a').write(_json_dbg.dumps({"sessionId":"02279c","hypothesisId":"H4","location":"routes.py:api_delete_photo","message":"delete album photo EXCEPTION","data":{"page_id":page_id,"error":str(e)},"timestamp":__import__('time').time()})+'\n')
        # #endregion
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/restore-photo', methods=['POST'])
def api_restore_workspace_photo():
    """Restore a workspace photo from the trash. Also refreshes photo_count."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        data = request.get_json() or {}
        token = data.get('trash_token')
        if not token:
            return jsonify({'success': False, 'error': 'No trash_token provided'}), 400

        restored, payload_meta = restore_from_trash(workspace, token)

        # Update photo_count in the page's YAML
        page_folder = restored.parent
        config_path = page_folder / "page_config.yaml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                page_data = yaml.safe_load(f) or {}
            remaining_images = [
                p for p in page_folder.iterdir()
                if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
            ]
            page_data['photo_count'] = len(remaining_images)
            if 'photo_captions' not in page_data:
                page_data['photo_captions'] = {}
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(page_data, f, allow_unicode=True, default_flow_style=False)

        # If the trashed entry was a photo with a tracked manifest entry,
        # rebuild that entry and clear the tombstone so sync stops skipping it.
        if payload_meta.get("kind") == "photo":
            source_path = payload_meta.get("source_path") or ""
            if source_path:
                add_photo_to_manifest(
                    page_folder,
                    payload_meta.get("image_name") or restored.name,
                    source_path=source_path,
                    source_mtime=float(payload_meta.get("source_mtime") or 0.0),
                    sha1=str(payload_meta.get("sha1") or ""),
                    section_id=str(payload_meta.get("section_id") or "") or None,
                )
                remove_tombstone(
                    workspace,
                    str(payload_meta.get("section_id") or ""),
                    source_path,
                )

        return jsonify({'success': True, 'restored_path': str(restored.relative_to(workspace))})

    except FileNotFoundError as e:
        return jsonify({'success': False, 'error': str(e)}), 404
    except FileExistsError as e:
        return jsonify({'success': False, 'error': str(e)}), 409
    except Exception as e:
        logger.error(f"Failed to restore photo: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/page/<page_id>/delete', methods=['DELETE'])
def api_delete_page(page_id):
    """Delete an entire page."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        page_folder = workspace / page_id
        
        if not page_folder.exists():
            return jsonify({'success': False, 'error': 'Page not found'}), 404
        
        result = delete_page(workspace, page_folder)

        if result['success']:
            return jsonify({
                'success': True,
                'last_in_section': result['last_in_section'],
                'renumbered': result['renumbered'],
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to delete page'}), 500
            
    except Exception as e:
        logger.error(f"Failed to delete page {page_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/page/<page_id>/title', methods=['PUT'])
def api_update_title(page_id):
    """Update page title."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        page_folder = workspace / page_id
        
        if not page_folder.exists():
            return jsonify({'success': False, 'error': 'Page not found'}), 404
        
        data = request.get_json()
        new_titles = data.get('titles', [])
        
        if not isinstance(new_titles, list):
            new_titles = [new_titles] if new_titles else []
        
        success = update_page_title(page_folder, new_titles)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to update title'}), 500
            
    except Exception as e:
        logger.error(f"Failed to update title for {page_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/page/<page_id>/layout-mode', methods=['PUT'])
def api_update_layout_mode(page_id):
    """Update page layout mode."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        page_folder = workspace / page_id
        
        if not page_folder.exists():
            return jsonify({'success': False, 'error': 'Page not found'}), 404
        
        data = request.get_json()
        layout_mode = data.get('layout_mode', 'mesa_de_luz')
        
        config_path = page_folder / "page_config.yaml"
        if not config_path.exists():
            return jsonify({'success': False, 'error': 'Config not found'}), 404
        
        with open(config_path, 'r', encoding='utf-8') as f:
            yaml_data = yaml.safe_load(f) or {}
        
        yaml_data['layout_mode'] = layout_mode
        
        if 'photo_captions' not in yaml_data:
            yaml_data['photo_captions'] = {}
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False)
        
        logger.info(f"Updated layout_mode for {page_id} to {layout_mode}")
        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Failed to update layout mode for {page_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/page/<page_id>/shuffle-layout', methods=['POST'])
def api_shuffle_layout(page_id):
    """Shuffle photos into a random order AND change layout_seed; regenerate preview."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        page_folder = workspace / page_id

        if not page_folder.exists():
            return jsonify({'success': False, 'error': 'Page not found'}), 404

        images = sorted(
            p for p in page_folder.iterdir()
            if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
        )
        if not images:
            return jsonify({'success': False, 'error': 'No images in page'}), 400

        names = [p.name for p in images]
        shuffled = names[:]
        attempts = 0
        while shuffled == names and len(names) > 1 and attempts < 20:
            random.shuffle(shuffled)
            attempts += 1

        if len(names) > 1:
            success = reorder_photos(page_folder, shuffled)
            if not success:
                return jsonify({'success': False, 'error': 'Failed to reorder photos'}), 500

        # Also change layout_seed so decorative randomness (rotation/jitter/z) changes too
        config_path = page_folder / "page_config.yaml"
        new_seed = None
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml_data = yaml.safe_load(f) or {}
            previous_seed = yaml_data.get('layout_seed')
            new_seed = random.randint(0, 2**31 - 1)
            if new_seed == previous_seed:
                new_seed = (new_seed + 1) % (2**31)
            yaml_data['layout_seed'] = new_seed
            if 'photo_captions' not in yaml_data:
                yaml_data['photo_captions'] = {}
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False)

        # Regenerate preview PDF immediately so the frontend iframe reload sees fresh content
        global_cfg, _ = load_workspace(workspace)
        generate_preview(page_folder, global_cfg)

        logger.info(f"Shuffled {len(shuffled)} photos + seed={new_seed} in {page_id}")
        return jsonify({'success': True, 'order': shuffled, 'layout_seed': new_seed})

    except Exception as e:
        logger.error(f"Failed to shuffle photos for {page_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/page/<page_id>/caption', methods=['PUT'])
def api_update_caption(page_id):
    """Update caption for a specific photo."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        page_folder = workspace / page_id
        
        if not page_folder.exists():
            return jsonify({'success': False, 'error': 'Page not found'}), 404
        
        data = request.get_json()
        filename = data.get('filename')
        caption = data.get('caption', '')
        
        if not filename:
            return jsonify({'success': False, 'error': 'No filename provided'}), 400
        
        success = update_photo_caption(page_folder, filename, caption)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to update caption'}), 500
            
    except Exception as e:
        logger.error(f"Failed to update caption for {page_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/page/<page_id>/regenerate', methods=['POST'])
def api_regenerate_page(page_id):
    """Regenerate page preview PDF."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        page_folder = workspace / page_id
        
        if not page_folder.exists():
            return jsonify({'success': False, 'error': 'Page not found'}), 404
        
        global_cfg, _ = load_workspace(workspace)
        preview_path = generate_preview(page_folder, global_cfg)
        
        if preview_path:
            return jsonify({'success': True, 'preview': str(preview_path)})
        else:
            return jsonify({'success': False, 'error': 'Failed to generate preview'}), 500
            
    except Exception as e:
        logger.error(f"Failed to regenerate page {page_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/page/<page_id>/preview', methods=['GET'])
def api_get_preview(page_id):
    """Serve the preview PDF for a page."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        page_folder = workspace / page_id
        
        if not page_folder.exists():
            return jsonify({'success': False, 'error': 'Page not found'}), 404
        
        # Look for page_XX.pdf in the folder
        pdf_files = list(page_folder.glob('page_*.pdf'))
        
        if not pdf_files:
            # Generate preview if it doesn't exist
            global_cfg, _ = load_workspace(workspace)
            preview_path = generate_preview(page_folder, global_cfg)
            if not preview_path:
                return jsonify({'success': False, 'error': 'No preview available'}), 404
        else:
            # Pick the most recently modified PDF as a safety net for folders
            # that still have stale page_<old>.pdf files from prior renumbering.
            preview_path = max(pdf_files, key=lambda p: p.stat().st_mtime)
        
        return send_file(
            preview_path,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=f'{page_id}_preview.pdf'
        )
        
    except Exception as e:
        logger.error(f"Failed to serve preview for {page_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/page/<page_id>/explode', methods=['POST'])
def api_explode_page(page_id):
    """Split a page into two: first half stays, second half moves to a new page right after."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        result = explode_page(workspace, page_id)
        if result.get('success'):
            return jsonify(result)
        return jsonify({'success': False, 'error': result.get('error', 'Error desconocido')}), 400
    except Exception as e:
        logger.error(f"Failed to explode page {page_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/page/<page_id>/completed', methods=['PUT'])
def api_set_page_completed(page_id):
    """Set or unset the 'completed' review flag for a page."""
    try:
        workspace = Path(current_app.config['WORKSPACE'])
        page_folder = workspace / page_id

        if not page_folder.exists():
            return jsonify({'success': False, 'error': 'Page not found'}), 404

        data = request.get_json() or {}
        completed = bool(data.get('completed', False))

        config_path = page_folder / "page_config.yaml"
        if not config_path.exists():
            return jsonify({'success': False, 'error': 'Config not found'}), 404

        with open(config_path, 'r', encoding='utf-8') as f:
            yaml_data = yaml.safe_load(f) or {}

        yaml_data['completed'] = completed

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False)

        logger.info(f"Set completed={completed} for page {page_id}")
        return jsonify({'success': True, 'completed': completed})

    except Exception as e:
        logger.error(f"Failed to set completed for {page_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/save', methods=['POST'])
def api_save_changes():
    """Save all pending changes (placeholder for manual save functionality)."""
    try:
        # In the current implementation, changes are immediately persisted
        # This endpoint is here for future enhancements (e.g., transaction-based edits)
        return jsonify({'success': True, 'message': 'Changes saved'})
    except Exception as e:
        logger.error(f"Failed to save changes: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/discard', methods=['POST'])
def api_discard_changes():
    """Discard all pending changes (placeholder for manual save functionality)."""
    try:
        # In the current implementation, changes are immediately persisted
        # This endpoint is here for future enhancements (e.g., transaction-based edits)
        return jsonify({'success': True, 'message': 'Changes discarded'})
    except Exception as e:
        logger.error(f"Failed to discard changes: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/page/<page_id>/image/<path:filename>', methods=['GET'])
def api_serve_page_image(page_id, filename):
    """Serve a photo from a page folder in the workspace."""
    try:
        workspace = Path(current_app.config['WORKSPACE']).resolve()
        page_folder = (workspace / page_id).resolve()

        try:
            page_folder.relative_to(workspace)
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid page'}), 400

        if not page_folder.exists() or not page_folder.is_dir():
            return jsonify({'success': False, 'error': 'Page not found'}), 404

        photo_path = (page_folder / filename).resolve()
        try:
            photo_path.relative_to(page_folder)
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid filename'}), 400

        if not photo_path.exists() or not photo_path.is_file():
            return jsonify({'success': False, 'error': 'File not found'}), 404

        if photo_path.suffix.lower() not in VALID_IMAGE_EXTENSIONS:
            return jsonify({'success': False, 'error': 'Not an image'}), 400

        return send_file(photo_path, as_attachment=False, download_name=photo_path.name)

    except Exception as e:
        logger.error(f"Failed to serve page image {page_id}/{filename}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
