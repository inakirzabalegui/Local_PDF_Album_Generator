"""API routes for Source mode folder and photo management."""

from __future__ import annotations

import logging
from pathlib import Path

from flask import jsonify, request, send_file, current_app

from src.editor.app import app
from src.editor.source_manager import (
    list_event_folders,
    list_photos,
    get_event_info,
    delete_photo,
    delete_folder,
    rename_folder_and_photos,
    regenerate_album,
)

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
        
        if not filename:
            return jsonify({'success': False, 'error': 'No filename provided'}), 400
        
        success = delete_photo(folder_path, filename)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to delete photo'}), 500
            
    except Exception as e:
        logger.error(f"Failed to delete photo from {folder_name}: {e}")
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
        
        success = delete_folder(source, folder_name)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to delete folder'}), 500
            
    except Exception as e:
        logger.error(f"Failed to delete source folder {folder_name}: {e}")
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
        
        # For POST, require confirmation if workspace exists
        if workspace.exists():
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
