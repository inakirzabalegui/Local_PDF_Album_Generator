"""Flask application for the interactive page editor and unified app."""

from __future__ import annotations

import logging
import queue
import threading
import webbrowser
from pathlib import Path

from flask import Flask, render_template, jsonify, request, current_app

from src.editor.workspace_manager import load_workspace

logger = logging.getLogger("album.editor")

# Create Flask app
app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # Disable caching for development

# Global state for the unified app
_folder_picker_queue: queue.Queue | None = None

# Import routes to register them
from src.editor import routes  # noqa: F401, E402
from src.editor import source_routes  # noqa: F401, E402


def validate_workspace(workspace_path: Path) -> bool:
    """Check if path is a valid album workspace.

    Args:
        workspace_path: Path to check

    Returns:
        True if valid workspace, False otherwise
    """
    return (workspace_path / "global_config.yaml").exists()


@app.route("/")
def index():
    """Serve the launcher or legacy editor depending on context."""
    # If WORKSPACE is set but SOURCE is not, we're in legacy --edit mode
    if "WORKSPACE" in app.config and "SOURCE" not in app.config:
        return legacy_editor_index()
    # If both SOURCE and WORKSPACE are set, we're in unified app mode
    elif "SOURCE" in app.config and "WORKSPACE" in app.config:
        return app_index()
    # Otherwise show launcher
    else:
        return render_template("launcher.html")


def legacy_editor_index():
    """Serve the legacy editor interface (for --edit mode)."""
    workspace = Path(app.config["WORKSPACE"])
    global_cfg, pages = load_workspace(workspace)

    # Filter out cover and backcover, sort by page number
    content_pages = [p for p in pages if not p.is_cover and not p.is_backcover]
    content_pages.sort(key=lambda p: p.page_number)

    return render_template(
        "editor.html",
        album_title=global_cfg.project_title,
        total_pages=len(content_pages),
        pages=[
            {
                "id": p.folder.name,
                "number": p.page_number,
                "title": p.section_titles[0]
                if p.section_titles
                else f"Page {p.page_number}",
                "photo_count": p.photo_count,
            }
            for p in content_pages
        ],
    )


def app_index():
    """Serve the main app interface (with Fuente/Edición tabs)."""
    workspace = Path(app.config.get("WORKSPACE"))
    # #region agent log
    import json as _json_dbg; open('/Users/jzabalegui/Coding/Local_PDF_Album_Generator/.cursor/debug-02279c.log','a').write(_json_dbg.dumps({"sessionId":"02279c","hypothesisId":"H1,H2","location":"app.py:app_index","message":"app_index called","data":{"workspace":str(workspace),"exists":workspace.exists(),"has_global_config":(workspace/"global_config.yaml").exists()},"timestamp":__import__('time').time()})+'\n')
    # #endregion
    if not (workspace / "global_config.yaml").exists():
        logger.warning(f"global_config.yaml missing in {workspace}, showing empty app")
        return render_template(
            "app.html",
            album_title="(álbum pendiente)",
            total_pages=0,
            has_pages=False,
            pages=[],
        )
    global_cfg, pages = load_workspace(workspace)

    # Filter out cover and backcover, sort by page number
    content_pages = [p for p in pages if not p.is_cover and not p.is_backcover]
    content_pages.sort(key=lambda p: p.page_number)

    return render_template(
        "app.html",
        album_title=global_cfg.project_title,
        total_pages=len(content_pages),
        has_pages=len(content_pages) > 0,
        pages=[
            {
                "id": p.folder.name,
                "number": p.page_number,
                "title": p.section_titles[0]
                if p.section_titles
                else f"Page {p.page_number}",
                "photo_count": p.photo_count,
                "layout_mode": p.layout_mode,
                "completed": p.completed,
            }
            for p in content_pages
        ],
    )


@app.route("/app")
def app_view():
    """Serve the unified app interface after bootstrap."""
    if "WORKSPACE" not in app.config:
        return jsonify({"error": "No workspace configured"}), 400
    return app_index()


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


@app.route("/api/pick-folder", methods=["POST"])
def api_pick_folder():
    """Show native file picker dialog.

    Uses osascript on macOS (always available), falls back to tkinter.

    Returns:
        JSON with 'path' if successful, 'error' if failed or cancelled
    """
    import sys
    import subprocess

    # Strategy 1: macOS osascript (native, always available; avoids tkinter dependency)
    if sys.platform == "darwin":
        try:
            script = (
                'tell application "System Events"\n'
                "    activate\n"
                "    try\n"
                '        set folderPath to POSIX path of (choose folder with prompt "Selecciona carpeta con fotos")\n'
                "        return folderPath\n"
                "    on error number -128\n"
                '        return ""\n'
                "    end try\n"
                "end tell"
            )
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=120
            )

            if result.returncode == 0:
                folder_path = result.stdout.strip()
                # Remove trailing slash if present
                if folder_path.endswith("/") and folder_path != "/":
                    folder_path = folder_path.rstrip("/")

                if folder_path:
                    return jsonify({"success": True, "path": folder_path})
                else:
                    return jsonify(
                        {"success": False, "error": "Selección cancelada"}
                    ), 400
            else:
                logger.warning(f"osascript failed: {result.stderr}")
        except Exception as e:
            logger.warning(f"osascript exception: {e}")

    # Strategy 2: tkinter fallback (may not be available in Homebrew Python)
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        folder_path = filedialog.askdirectory(
            title="Selecciona carpeta con fotos", initialdir=str(Path.home())
        )

        root.destroy()

        if folder_path:
            return jsonify({"success": True, "path": folder_path})
        else:
            return jsonify({"success": False, "error": "Selección cancelada"}), 400

    except Exception as e:
        logger.error(f"All folder pickers failed: {e}")
        return jsonify(
            {
                "success": False,
                "error": "No se pudo abrir el diálogo de selección. Pega la ruta manualmente.",
            }
        ), 500


@app.route("/api/bootstrap", methods=["POST"])
def api_bootstrap():
    """Bootstrap the app: validate source, create workspace if needed.

    Expected JSON:
        { "source_path": "/path/to/source" }

    Returns:
        { "success": true, "redirect": "/app" }
    """
    data = request.get_json() or {}
    source_path_str = data.get("source_path", "").strip()

    # Strip surrounding quotes (single or double) — common when users paste from terminal
    if (
        len(source_path_str) >= 2
        and source_path_str[0] in ('"', "'")
        and source_path_str[-1] == source_path_str[0]
    ):
        source_path_str = source_path_str[1:-1]

    if not source_path_str:
        return jsonify({"success": False, "error": "No source_path provided"}), 400

    try:
        source_path = Path(source_path_str).resolve()

        if not source_path.is_dir():
            return jsonify(
                {"success": False, "error": f"'{source_path}' no es un directorio"}
            ), 400

        # Reject if user accidentally picked an _album workspace folder
        if (
            source_path.name.endswith("_album")
            or (source_path / "global_config.yaml").exists()
        ):
            return jsonify(
                {
                    "success": False,
                    "error": f"'{source_path.name}' parece ser un workspace de álbum, no una carpeta fuente. Selecciona la carpeta con tus fotos originales.",
                }
            ), 400

        # Check if folder contains at least one image
        from src.ingestion.scanner import VALID_EXTENSIONS

        has_image = any(
            p.is_file() and p.suffix.lower() in VALID_EXTENSIONS
            for p in source_path.rglob("*")
        )

        if not has_image:
            return jsonify(
                {"success": False, "error": "No se encontraron imágenes en la carpeta"}
            ), 400

        # Calculate workspace path
        workspace = source_path.parent / f"{source_path.name}_album"

        album_generated = True
        if not workspace.exists():
            logger.info(f"Scaffolding workspace: {workspace}")
            _scaffold_workspace(source_path, workspace)
            album_generated = False
        else:
            logger.info(f"Using existing workspace: {workspace}")

        # Empty the trash of the *previous* album if the user switched folders.
        # Reopening the same source keeps its trash (undo survives restarts).
        previous_source = app.config.get("SOURCE")
        previous_workspace = app.config.get("WORKSPACE")
        if previous_source and previous_source != str(source_path):
            from src.editor.trash import empty_trash

            try:
                empty_trash(Path(previous_source))
                if previous_workspace:
                    empty_trash(Path(previous_workspace))
            except Exception as e:
                logger.warning(f"Could not empty previous trash: {e}")

        app.config["SOURCE"] = str(source_path)
        app.config["WORKSPACE"] = str(workspace)

        redirect_url = "/app?pending=1" if not album_generated else "/app"
        return jsonify({"success": True, "redirect": redirect_url, "album_generated": album_generated})

    except Exception as e:
        logger.error(f"Bootstrap failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def _scaffold_workspace(source_path: Path, workspace: Path) -> None:
    """Create a minimal workspace: folder + log + default global_config.yaml.

    Does NOT scan photos or create page folders. The user triggers generation
    explicitly later via the Source tab.
    """
    import re
    from src.workspace.config import GlobalConfig, write_global_config
    from src.utils.logger import setup_logger

    workspace.mkdir(parents=True, exist_ok=True)
    logger_instance = setup_logger(workspace, "bootstrap")

    # Derive a human-readable title from the source folder name
    name = source_path.name
    clean = re.sub(r"^\d{8}_", "", name)
    title = clean.replace("_", " ").strip() or name

    write_global_config(workspace, GlobalConfig(project_title=title))
    logger_instance.info(
        f"Workspace inicializado en '{workspace}'. La generación de páginas está pendiente."
    )


def _bootstrap_workspace(source_path: Path, workspace: Path) -> None:
    """Execute the workspace initialization pipeline.

    Invokes the same functions as --init to create workspace.
    """
    from src.ingestion.scanner import scan_directory
    from src.ingestion.sorter import sort_photos
    from src.workspace.initializer import create_workspace
    from src.workspace.config import write_global_config, write_page_configs
    from src.utils.logger import setup_logger

    workspace.mkdir(parents=True, exist_ok=True)
    logger_instance = setup_logger(workspace, "bootstrap")

    logger_instance.info(f"Escaneando '{source_path}' …")
    scan_result = scan_directory(source_path)

    if scan_result.cover_photos:
        logger_instance.info(
            f"✓ Carpeta 'portada' encontrada: {len(scan_result.cover_photos)} foto(s)"
        )
    else:
        logger_instance.info("○ Carpeta 'portada' no encontrada")

    if scan_result.backcover_photos:
        logger_instance.info(
            f"✓ Carpeta 'contraportada' encontrada: {len(scan_result.backcover_photos)} foto(s)"
        )
    else:
        logger_instance.info("○ Carpeta 'contraportada' no encontrada")

    if not scan_result.photos:
        raise RuntimeError("No se encontraron imágenes válidas")

    logger_instance.info(f"{len(scan_result.photos)} imágenes encontradas. Ordenando …")
    sorted_photos = sort_photos(scan_result.photos)

    logger_instance.info(f"Creando workspace en '{workspace}' …")
    global_cfg, page_map = create_workspace(
        sorted_photos,
        workspace,
        source_dir_name=source_path.name,
        cover_candidates=scan_result.cover_photos,
        backcover_candidates=scan_result.backcover_photos,
    )

    write_global_config(workspace, global_cfg)
    write_page_configs(page_map)

    total_pages = len(page_map)
    logger_instance.info(f"Workspace creado con {total_pages} página(s).")
    if total_pages < 24:
        logger_instance.warning(
            f"El álbum tiene solo {total_pages} página(s). "
            f"Peecho requiere un mínimo de 24 páginas — se añadirán páginas en blanco al renderizar."
        )


def launch_editor(workspace_path: Path, port: int = 5050, auto_open: bool = True):
    """Start the Flask editor server and optionally open browser (legacy mode).

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
    app.config["WORKSPACE"] = str(workspace_path)

    print(f"🚀 Iniciando editor interactivo...")
    print(f"📁 Workspace: {workspace_path.name}")
    print(f"🌐 URL: http://localhost:{port}")
    print(f"")
    print(f"Presiona Ctrl+C para detener el servidor")
    print(f"")

    # Open browser
    if auto_open:
        webbrowser.open(f"http://localhost:{port}")

    # Run Flask app
    app.run(host="localhost", port=port, debug=False)


def launch_app(port: int = 5050, auto_open: bool = True):
    """Start the unified app with Fuente and Edición modes.

    Args:
        port: Port to run the server on (default: 5050)
        auto_open: Whether to automatically open browser (default: True)
    """
    print(f"🚀 Iniciando aplicación unificada...")
    print(f"🌐 URL: http://localhost:{port}")
    print(f"")
    print(f"Presiona Ctrl+C para detener el servidor")
    print(f"")

    # Open browser in background thread after server is ready
    if auto_open:

        def _open_browser():
            import time

            # Poll until the server responds before opening browser
            import urllib.request

            for _ in range(20):
                try:
                    urllib.request.urlopen(f"http://localhost:{port}/", timeout=1)
                    break
                except Exception:
                    time.sleep(0.3)
            webbrowser.open(f"http://localhost:{port}")

        threading.Thread(target=_open_browser, daemon=True).start()

    # Run Flask app
    app.run(host="localhost", port=port, debug=False)
