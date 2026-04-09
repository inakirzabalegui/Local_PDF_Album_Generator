"""Flask application for the interactive page editor."""

from __future__ import annotations

import logging
import webbrowser
from pathlib import Path

from flask import Flask, render_template, jsonify

from src.editor.workspace_manager import load_workspace

logger = logging.getLogger("album.editor")

# Create Flask app
app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable caching for development

# Import routes to register them
from src.editor import routes  # noqa: F401, E402


def validate_workspace(workspace_path: Path) -> bool:
    """Check if path is a valid album workspace.
    
    Args:
        workspace_path: Path to check
        
    Returns:
        True if valid workspace, False otherwise
    """
    return (workspace_path / "global_config.yaml").exists()


@app.route('/')
def index():
    """Serve the main editor interface."""
    workspace = Path(app.config['WORKSPACE'])
    global_cfg, pages = load_workspace(workspace)
    
    # Filter out cover and backcover, sort by page number
    content_pages = [p for p in pages if not p.is_cover and not p.is_backcover]
    content_pages.sort(key=lambda p: p.page_number)
    
    return render_template(
        'editor.html',
        album_title=global_cfg.project_title,
        total_pages=len(content_pages),
        pages=[{
            'id': p.folder.name,
            'number': p.page_number,
            'title': p.section_titles[0] if p.section_titles else f"Page {p.page_number}",
            'photo_count': p.photo_count,
        } for p in content_pages]
    )


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})


def launch_editor(workspace_path: Path, port: int = 5050, auto_open: bool = True):
    """Start the Flask editor server and optionally open browser.
    
    Args:
        workspace_path: Path to the album workspace
        port: Port to run the server on (default: 5050)
        auto_open: Whether to automatically open browser (default: True)
    """
    # Validate workspace
    if not validate_workspace(workspace_path):
        print(f"❌ Error: '{workspace_path}' no es un workspace válido.")
        print(f"   Falta el archivo 'global_config.yaml'")
        return
    
    # Set workspace path in app config
    app.config['WORKSPACE'] = str(workspace_path)
    
    print(f"🚀 Iniciando editor interactivo...")
    print(f"📁 Workspace: {workspace_path.name}")
    print(f"🌐 URL: http://localhost:{port}")
    print(f"")
    print(f"Presiona Ctrl+C para detener el servidor")
    print(f"")
    
    # Open browser
    if auto_open:
        webbrowser.open(f'http://localhost:{port}')
    
    # Run Flask app
    app.run(host='localhost', port=port, debug=False)
