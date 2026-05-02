"""API routes for Source mode folder and photo management."""

from __future__ import annotations

import json
import logging
import queue
import threading
from pathlib import Path

from flask import jsonify, request, send_file, current_app, Response, stream_with_context

from src.editor.app import app
from src.editor.source_manager import (
    list_event_folders,
    list_photos,
    get_event_info,
    delete_photo,
    delete_folder,
    rename_folder_and_photos,
    move_photos_to_folder,
    regenerate_album,
    is_regeneration_running,
    read_event_completed,
    write_event_completed,
)
from src.editor.trash import restore_from_trash

logger = logging.getLogger("album.editor.source")


@app.route('/api/source/folders', methods=['GET'])
def api_list_source_folders():
    """List all event folders in the source directory."""
    try:
        source = Path(current_app.config.get('SOURCE'))
        if not source:
            return jsonify({'success': False, 'error': 'No source configured'}), 400
        
        folders = list_event_folders(source)
        
        return jsonify({
            'success': True,
            'folders': folders
        })
    except Exception as e:
        logger.error(f"Failed to list source folders: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/source/folder/<folder_name>', methods=['GET'])
def api_get_source_folder(folder_name):
    """Get details about a specific event folder."""
    try:
        source = Path(current_app.config.get('SOURCE'))
        if not source:
            return jsonify({'success': False, 'error': 'No source configured'}), 400
        
        folder_path = source / folder_name
        if not folder_path.exists():
            return jsonify({'success': False, 'error': 'Folder not found'}), 404
        
        info = get_event_info(folder_path)
        
        return jsonify({
            'success': True,
            'folder': info
        })
    except Exception as e:
        logger.error(f"Failed to get source folder {folder_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/source/folder/<folder_name>/photo', methods=['DELETE'])
def api_delete_source_photo(folder_name):
    """Delete a photo from an event folder."""
    try:
        source = Path(current_app.config.get('SOURCE'))
        if not source:
            return jsonify({'success': False, 'error': 'No source configured'}), 400
        
        folder_path = source / folder_name
        if not folder_path.exists():
            return jsonify({'success': False, 'error': 'Folder not found'}), 404
        
        data = request.get_json() or {}
        filename = data.get('filename')
        subfolder = (data.get('subfolder') or '').strip()

        if not filename:
            return jsonify({'success': False, 'error': 'No filename provided'}), 400

        # #region agent log
        import json as _json_dbg; open('/Users/jzabalegui/Coding/Local_PDF_Album_Generator/.cursor/debug-02279c.log','a').write(_json_dbg.dumps({"sessionId":"02279c","hypothesisId":"H4","location":"source_routes.py:api_delete_source_photo","message":"delete source photo","data":{"folder":folder_name,"subfolder":subfolder,"filename":filename,"source":str(source),"photo_exists":(folder_path/subfolder/filename if subfolder else folder_path/filename).exists()},"timestamp":__import__('time').time()})+'\n')
        # #endregion

        token = delete_photo(folder_path, filename, source, subfolder=subfolder)

        if token is not None:
            return jsonify({
                'success': True,
                'trash_token': token.token_id,
                'trash_scope': 'source',
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to delete photo'}), 500

    except Exception as e:
        logger.error(f"Failed to delete photo from {folder_name}: {e}")
        # #region agent log
        import json as _json_dbg; open('/Users/jzabalegui/Coding/Local_PDF_Album_Generator/.cursor/debug-02279c.log','a').write(_json_dbg.dumps({"sessionId":"02279c","hypothesisId":"H4","location":"source_routes.py:api_delete_source_photo","message":"delete source photo EXCEPTION","data":{"folder":folder_name,"error":str(e)},"timestamp":__import__('time').time()})+'\n')
        # #endregion
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/source/folder/<folder_name>', methods=['DELETE'])
def api_delete_source_folder(folder_name):
    """Delete an entire event folder."""
    try:
        source = Path(current_app.config.get('SOURCE'))
        if not source:
            return jsonify({'success': False, 'error': 'No source configured'}), 400
        
        folder_path = source / folder_name
        if not folder_path.exists():
            return jsonify({'success': False, 'error': 'Folder not found'}), 404
        
        # Require force parameter for safety
        force = request.args.get('force') == 'true'
        if not force:
            return jsonify({'success': False, 'error': 'Deletion not confirmed'}), 400
        
        token = delete_folder(source, folder_name)

        if token is not None:
            return jsonify({
                'success': True,
                'trash_token': token.token_id,
                'trash_scope': 'source',
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to delete folder'}), 500

    except Exception as e:
        logger.error(f"Failed to delete source folder {folder_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/source/restore', methods=['POST'])
def api_restore_source():
    """Restore a source photo or event folder from the source trash."""
    try:
        source = Path(current_app.config.get('SOURCE'))
        if not source:
            return jsonify({'success': False, 'error': 'No source configured'}), 400

        data = request.get_json() or {}
        token = data.get('trash_token')
        if not token:
            return jsonify({'success': False, 'error': 'No trash_token provided'}), 400

        restored = restore_from_trash(source, token)
        return jsonify({'success': True, 'restored_path': str(restored.relative_to(source))})

    except FileNotFoundError as e:
        return jsonify({'success': False, 'error': str(e)}), 404
    except FileExistsError as e:
        return jsonify({'success': False, 'error': str(e)}), 409
    except Exception as e:
        logger.error(f"Failed to restore from source trash: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/source/folder/<folder_name>/rename', methods=['PUT'])
def api_rename_source_folder(folder_name):
    """Rename an event folder and renumber all photos inside."""
    try:
        source = Path(current_app.config.get('SOURCE'))
        if not source:
            return jsonify({'success': False, 'error': 'No source configured'}), 400
        
        folder_path = source / folder_name
        if not folder_path.exists():
            return jsonify({'success': False, 'error': 'Folder not found'}), 404
        
        data = request.get_json() or {}
        new_name = data.get('new_name', '').strip()
        
        if not new_name:
            return jsonify({'success': False, 'error': 'No new_name provided'}), 400
        
        success = rename_folder_and_photos(source, folder_name, new_name)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to rename folder'}), 500
            
    except Exception as e:
        logger.error(f"Failed to rename source folder {folder_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/source/folder/<folder_name>/move-photos', methods=['POST'])
def api_move_source_photos(folder_name):
    """Move photos from one event folder to another, renumbering the destination."""
    try:
        source = Path(current_app.config.get('SOURCE'))
        if not source:
            return jsonify({'success': False, 'error': 'No source configured'}), 400

        data = request.get_json() or {}
        target_folder = data.get('target_folder', '').strip()
        filenames = data.get('filenames', [])

        if not target_folder or not filenames:
            return jsonify({'success': False, 'error': 'Missing target_folder or filenames'}), 400

        if not (source / folder_name).exists():
            return jsonify({'success': False, 'error': 'Source folder not found'}), 404
        if not (source / target_folder).exists():
            return jsonify({'success': False, 'error': 'Target folder not found'}), 404

        success = move_photos_to_folder(source, folder_name, target_folder, filenames)

        if success:
            # Return updated photo lists for both folders so the UI can refresh
            from src.editor.source_manager import get_event_info as _info
            return jsonify({
                'success': True,
                'source_folder': _info(source / folder_name),
                'target_folder': _info(source / target_folder),
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to move photos'}), 500

    except Exception as e:
        logger.error(f"Failed to move source photos from {folder_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/source/regenerate-album', methods=['POST', 'GET'])
def api_regenerate_source_album():
    """Regenerate the album from source photos."""
    try:
        source = Path(current_app.config.get('SOURCE'))
        workspace = Path(current_app.config.get('WORKSPACE'))
        
        if not source or not workspace:
            return jsonify({'success': False, 'error': 'Source or workspace not configured'}), 400
        
        # For GET with ?check=true, just check if workspace exists
        if request.method == 'GET':
            check = request.args.get('check') == 'true'
            if check:
                return jsonify({
                    'success': True,
                    'exists': workspace.exists()
                })

        if is_regeneration_running():
            return jsonify({'success': False, 'error': 'Ya hay una generación en curso. Espera a que termine.'}), 409
        
        # Require confirmation only if workspace has real page folders AND a valid config
        workspace_is_valid = workspace.exists() and (workspace / "global_config.yaml").exists()
        has_real_pages = workspace_is_valid and bool(list(workspace.glob('pagina_*')))
        if has_real_pages:
            data = request.get_json() or {}
            if not data.get('confirm'):
                return jsonify({
                    'success': False,
                    'error': 'Workspace exists. Requires confirmation.'
                }), 400
        
        logger.info(f"Regenerating album from {source} to {workspace}")
        success = regenerate_album(source, workspace)
        
        if success:
            # Return updated pages data
            from src.editor.workspace_manager import load_workspace
            try:
                global_cfg, pages = load_workspace(workspace)
                content_pages = [p for p in pages if not p.is_cover and not p.is_backcover]
                content_pages.sort(key=lambda p: p.page_number)
                
                pages_data = [{
                    'id': p.folder.name,
                    'number': p.page_number,
                    'title': p.section_titles[0] if p.section_titles else f"Page {p.page_number}",
                    'photo_count': p.photo_count,
                    'layout_mode': p.layout_mode,
                } for p in content_pages]
                
                return jsonify({
                    'success': True,
                    'pages': pages_data
                })
            except Exception as e:
                logger.warning(f"Could not load workspace after regen: {e}")
                return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to regenerate album'}), 500
            
    except Exception as e:
        logger.error(f"Failed to regenerate album: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/source/regenerate-album/stream', methods=['POST'])
def api_regenerate_source_album_stream():
    """Regenerate album with Server-Sent Events progress reporting."""
    try:
        source = Path(current_app.config.get('SOURCE'))
        workspace = Path(current_app.config.get('WORKSPACE'))

        if not source or not workspace:
            return jsonify({'success': False, 'error': 'Source or workspace not configured'}), 400

        if is_regeneration_running():
            return jsonify({'success': False, 'error': 'Ya hay una generación en curso. Espera a que termine.'}), 409

        data = request.get_json() or {}
        confirm = data.get('confirm', False)

        workspace_is_valid = workspace.exists() and (workspace / "global_config.yaml").exists()
        has_real_pages = workspace_is_valid and bool(list(workspace.glob('pagina_*')))
        if has_real_pages and not confirm:
            return jsonify({'success': False, 'error': 'Workspace exists. Requires confirmation.'}), 400

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    progress_queue: queue.Queue = queue.Queue()

    def _run():
        def _cb(event):
            progress_queue.put(event)

        try:
            success = regenerate_album(source, workspace, progress_callback=_cb)
            if success:
                from src.editor.workspace_manager import load_workspace as _lw
                try:
                    global_cfg, pages = _lw(workspace)
                    content = [p for p in pages if not p.is_cover and not p.is_backcover]
                    content.sort(key=lambda p: p.page_number)
                    pages_data = [
                        {
                            'id': p.folder.name,
                            'number': p.page_number,
                            'title': p.section_titles[0] if p.section_titles else f'Page {p.page_number}',
                            'photo_count': p.photo_count,
                            'layout_mode': p.layout_mode,
                        }
                        for p in content
                    ]
                except Exception:
                    pages_data = []
                progress_queue.put({'step': 'done', 'pages': pages_data})
            else:
                progress_queue.put({'step': 'error', 'message': 'Regeneración fallida'})
        except Exception as e:
            progress_queue.put({'step': 'error', 'message': str(e)})

    threading.Thread(target=_run, daemon=True).start()

    def _generate():
        while True:
            try:
                event = progress_queue.get(timeout=600)
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


@app.route('/api/source/folder/<folder_name>/completed', methods=['PUT'])
def api_set_source_folder_completed(folder_name):
    """Set or unset the 'completed' review flag for an event folder."""
    try:
        source = Path(current_app.config.get('SOURCE'))
        if not source:
            return jsonify({'success': False, 'error': 'No source configured'}), 400

        folder_path = source / folder_name
        if not folder_path.exists():
            return jsonify({'success': False, 'error': 'Folder not found'}), 404

        data = request.get_json() or {}
        completed = bool(data.get('completed', False))

        ok = write_event_completed(folder_path, completed)
        if ok:
            logger.info(f"Set completed={completed} for event {folder_name}")
            return jsonify({'success': True, 'completed': completed})
        else:
            return jsonify({'success': False, 'error': 'Failed to write metadata'}), 500

    except Exception as e:
        logger.error(f"Failed to set completed for {folder_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/source/image', methods=['GET'])
def api_serve_source_image():
    """Serve a source photo image with path validation."""
    try:
        source = Path(current_app.config.get('SOURCE'))
        if not source:
            return jsonify({'success': False, 'error': 'No source configured'}), 400
        
        path_str = request.args.get('path', '')
        if not path_str:
            return jsonify({'success': False, 'error': 'No path provided'}), 400
        
        # Decode and resolve the path
        photo_path = Path(path_str).resolve()
        
        # Security check: ensure the path is under the source directory
        try:
            photo_path.relative_to(source)
        except ValueError:
            logger.error(f"Attempted to access file outside source: {photo_path}")
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if not photo_path.exists():
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        if not photo_path.is_file():
            return jsonify({'success': False, 'error': 'Not a file'}), 400
        
        return send_file(
            photo_path,
            mimetype='image/jpeg',
            as_attachment=False,
            download_name=photo_path.name
        )
        
    except Exception as e:
        logger.error(f"Failed to serve source image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
