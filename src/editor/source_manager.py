"""Source folder management operations for the Source mode."""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    pass

from src.ingestion.scanner import scan_directory, VALID_EXTENSIONS
from src.ingestion.sorter import sort_photos
from src.utils.naming import prettify_folder_name, folder_name_to_slug, build_section_title
from src.workspace.initializer import create_workspace
from src.workspace.config import write_global_config, write_page_configs, read_global_config
from src.editor.trash import move_to_trash, TrashToken

logger = logging.getLogger("album.editor.source")

_regen_lock = threading.Lock()
_regen_running = False

_META_FILENAME = ".album_meta.yaml"


def read_event_completed(folder_path: Path) -> bool:
    """Read the 'completed' flag from .album_meta.yaml inside an event folder."""
    meta_path = folder_path / _META_FILENAME
    if not meta_path.exists():
        return False
    try:
        with open(meta_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return bool(data.get("completed", False))
    except Exception:
        return False


def write_event_completed(folder_path: Path, completed: bool) -> bool:
    """Write the 'completed' flag to .album_meta.yaml inside an event folder."""
    meta_path = folder_path / _META_FILENAME
    try:
        existing: dict = {}
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        existing["completed"] = completed
        with open(meta_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(existing, f, allow_unicode=True)
        return True
    except Exception as e:
        logger.error(f"Failed to write event meta: {e}")
        return False


def list_event_folders(source_path: Path) -> list[dict]:
    """List event folders (source_groups) in the source directory.
    
    Returns folders sorted by date prefix YYYYMMDD if present.
    Excludes portada/contraportada special folders.
    
    Args:
        source_path: Path to the source directory
        
    Returns:
        List of dicts with folder info
    """
    if not source_path.is_dir():
        return []
    
    folders = []
    
    for item in sorted(source_path.iterdir()):
        if not item.is_dir():
            continue
        
        # Skip special folders
        if item.name.lower() in ('portada', 'contraportada'):
            continue
        
        # Count photos in folder
        photos = [
            p for p in item.rglob('*')
            if p.is_file() and p.suffix.lower() in VALID_EXTENSIONS
        ]
        
        folders.append({
            'name': item.name,
            'folder': item.name,
            'path': str(item),
            'photo_count': len(photos),
            'completed': read_event_completed(item),
        })
    
    # Sort by date prefix if present
    def get_sort_key(f):
        name = f['name']
        if name[:8].isdigit():
            return (0, name[:8], name[8:])
        return (1, name, '')
    
    folders.sort(key=get_sort_key)
    
    return folders


def list_photos(folder_path: Path) -> list[str]:
    """List photos in a folder (top-level only), sorted alphabetically.

    Filenames produced during init already embed the capture date as a prefix,
    so alphabetical order equals chronological order.
    """
    if not folder_path.is_dir():
        return []

    return sorted(
        p.name
        for p in folder_path.iterdir()
        if p.is_file() and p.suffix.lower() in VALID_EXTENSIONS
    )


def list_event_sections(folder_path: Path) -> list[dict]:
    """List photo sections for an event folder.

    If the folder contains only top-level photos, returns a single section with
    no title. If it contains subfolders, returns one section per subfolder
    (titled by the subfolder's prettified name). Mixed cases prepend a titleless
    section for the top-level photos.

    Each section dict: {title, subfolder, photos}, where photos is a sorted
    list of filenames (basenames only) and subfolder is the relative subfolder
    name (empty string for top-level).
    """
    if not folder_path.is_dir():
        return []

    sections: list[dict] = []

    top_photos = list_photos(folder_path)
    if top_photos:
        sections.append({'title': '', 'subfolder': '', 'photos': top_photos})

    subfolders = sorted(
        (p for p in folder_path.iterdir() if p.is_dir()),
        key=lambda p: p.name,
    )
    for sub in subfolders:
        sub_photos = list_photos(sub)
        if not sub_photos:
            continue
        sections.append({
            'title': build_section_title(sub.name),
            'subfolder': sub.name,
            'photos': sub_photos,
        })

    return sections


def delete_photo(folder_path: Path, filename: str, source_root: Path, subfolder: str = '') -> TrashToken | None:
    """Move a source photo into the source trash.

    `subfolder` is a path relative to `folder_path` (empty for top-level).
    Returns a TrashToken on success, or None if the photo was not found /
    the operation failed.
    """
    try:
        photo_path = folder_path / subfolder / filename if subfolder else folder_path / filename
        if not photo_path.exists():
            logger.error(f"Photo not found: {subfolder}/{filename}" if subfolder else f"Photo not found: {filename}")
            return None

        token = move_to_trash(source_root, photo_path)
        logger.info(f"Trashed source photo: {subfolder}/{filename} (token {token.token_id})" if subfolder else f"Trashed source photo: {filename} (token {token.token_id})")
        return token

    except Exception as e:
        logger.error(f"Failed to delete photo: {e}")
        return None


def delete_folder(source_path: Path, folder_name: str) -> TrashToken | None:
    """Move an event folder into the source trash.

    Returns a TrashToken on success, or None otherwise.
    """
    try:
        folder_path = source_path / folder_name
        if not folder_path.exists():
            logger.error(f"Folder not found: {folder_name}")
            return None

        token = move_to_trash(source_path, folder_path)
        logger.info(f"Trashed folder: {folder_name} (token {token.token_id})")
        return token

    except Exception as e:
        logger.error(f"Failed to delete folder: {e}")
        return None


def rename_folder_and_photos(source_path: Path, old_name: str, new_name: str) -> bool:
    """Rename folder and renumber all photos inside with new prefix.
    
    The new prefix is derived from the folder name using folder_name_to_slug in CamelCase.
    Photos are renamed to {PREFIX}_{NNN}{ext} in chronological order.
    
    Args:
        source_path: Path to the source directory
        old_name: Current folder name
        new_name: New folder name
        
    Returns:
        True if successful, False otherwise
    """
    try:
        old_path = source_path / old_name
        new_path = source_path / new_name
        
        if not old_path.exists():
            logger.error(f"Folder not found: {old_name}")
            return False
        
        # Rename the folder itself
        old_path.rename(new_path)
        logger.info(f"Renamed folder: {old_name} -> {new_name}")
        
        # Get list of photos in chronological order
        photos = list_photos(new_path)
        
        if not photos:
            logger.info(f"No photos to rename in {new_name}")
            return True
        
        prefix = _folder_prefix(new_name)
        ok = _renumber_folder(new_path, prefix)
        if ok:
            logger.info(f"Renamed {len(photos)} photos in {new_name} with prefix {prefix}")
        return ok

    except Exception as e:
        logger.error(f"Failed to rename folder and photos: {e}")
        return False


def _folder_prefix(folder_name: str) -> str:
    """Use the full folder name as the prefix for photos (preserves date and underscores)."""
    return folder_name


def _renumber_folder(folder_path: Path, prefix: str) -> bool:
    """Renumber all photos in a folder with the given prefix ({PREFIX}_{NNN}{ext})."""
    photos = list_photos(folder_path)
    if not photos:
        return True

    temp_dir = folder_path / ".rename_tmp"
    temp_dir.mkdir(exist_ok=True)

    staged: list[Path] = []
    try:
        for seq, filename in enumerate(photos, 1):
            src = folder_path / filename
            ext = src.suffix.lower()
            if ext not in VALID_EXTENSIONS:
                ext = ".jpg"
            dst_temp = temp_dir / f"{prefix}_{seq:03d}{ext}"
            shutil.move(str(src), str(dst_temp))
            staged.append(dst_temp)

        for src_temp in staged:
            shutil.move(str(src_temp), str(folder_path / src_temp.name))
    except Exception:
        # Roll back: move staged files back to folder_path
        for f in temp_dir.iterdir():
            shutil.move(str(f), str(folder_path / f.name))
        temp_dir.rmdir()
        return False

    temp_dir.rmdir()
    return True


def move_photos_to_folder(
    source_path: Path,
    from_folder_name: str,
    to_folder_name: str,
    filenames: list[str],
) -> bool:
    """Move photos from one event folder to another and renumber the destination.

    The source folder is NOT renumbered (filenames stay consistent for the
    remaining photos).  The destination folder IS renumbered in full so that
    the moved photos get the target prefix and a clean sequential numbering.

    Args:
        source_path: Root source directory.
        from_folder_name: Folder name that owns the photos right now.
        to_folder_name: Target folder name.
        filenames: List of filenames to move (must exist in from_folder_name).

    Returns:
        True on success, False on any error.
    """
    try:
        from_path = source_path / from_folder_name
        to_path = source_path / to_folder_name

        if not from_path.exists():
            logger.error(f"Source folder not found: {from_folder_name}")
            return False
        if not to_path.exists():
            logger.error(f"Target folder not found: {to_folder_name}")
            return False

        for filename in filenames:
            src_file = from_path / filename
            if not src_file.exists():
                logger.warning(f"File not found, skipping: {filename}")
                continue
            # Use a temporary name to avoid collisions with existing files
            dst_file = to_path / filename
            if dst_file.exists():
                # Avoid overwriting: add a suffix
                stem, ext = dst_file.stem, dst_file.suffix
                dst_file = to_path / f"{stem}_moved{ext}"
            shutil.move(str(src_file), str(dst_file))
            logger.info(f"Moved {filename}: {from_folder_name} -> {to_folder_name}")

        # Renumber destination folder with target prefix
        prefix = _folder_prefix(to_folder_name)
        _renumber_folder(to_path, prefix)

        logger.info(f"Renumbered {to_folder_name} with prefix {prefix}")
        return True

    except Exception as e:
        logger.error(f"Failed to move photos: {e}")
        return False


def is_regeneration_running() -> bool:
    """Check if an album regeneration is currently in progress."""
    return _regen_running


def regenerate_album(source_path: Path, workspace_path: Path, progress_callback=None) -> bool:
    """Regenerate the album workspace from source photos.

    Args:
        source_path: Path to the source directory
        workspace_path: Path to the workspace directory
        progress_callback: Optional callable receiving progress dicts with keys
            step, current, total, name. Emitted at scanning, sorting, per-photo
            processing, writing_configs, and done.

    Returns:
        True if successful, False otherwise
    """
    global _regen_running

    if not _regen_lock.acquire(blocking=False):
        logger.warning("Regeneration already in progress, rejecting concurrent request")
        # #region agent log
        import json as _json_dbg; open('/Users/jzabalegui/Coding/Local_PDF_Album_Generator/.cursor/debug-02279c.log','a').write(_json_dbg.dumps({"sessionId":"02279c","hypothesisId":"H3","location":"source_manager.py:regenerate_album","message":"CONCURRENT regen rejected","data":{},"timestamp":__import__('time').time()})+'\n')
        # #endregion
        return False

    _regen_running = True
    # #region agent log
    import json as _json_dbg; open('/Users/jzabalegui/Coding/Local_PDF_Album_Generator/.cursor/debug-02279c.log','a').write(_json_dbg.dumps({"sessionId":"02279c","hypothesisId":"H3","location":"source_manager.py:regenerate_album","message":"regen START","data":{"source":str(source_path),"workspace":str(workspace_path)},"timestamp":__import__('time').time()})+'\n')
    # #endregion

    def _cb(event):
        if progress_callback:
            progress_callback(event)

    try:
        logger.info(f"Regenerating album: {workspace_path}")

        _cb({"step": "scanning"})

        # Scan source directory
        logger.info(f"Scanning source: {source_path}")
        scan_result = scan_directory(source_path)

        if not scan_result.photos:
            logger.warning("No photos found in source")
            return False

        # Sort photos
        logger.info(f"Sorting {len(scan_result.photos)} photos")
        _cb({"step": "sorting", "total": len(scan_result.photos)})
        sorted_photos = sort_photos(scan_result.photos)

        # Delete existing workspace if it exists
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
            logger.info(f"Deleted existing workspace")

        # Create workspace
        logger.info(f"Creating workspace: {workspace_path}")
        workspace_path.mkdir(parents=True, exist_ok=True)

        global_cfg, page_map = create_workspace(
            sorted_photos,
            workspace_path,
            source_dir_name=source_path.name,
            cover_candidates=scan_result.cover_photos,
            backcover_candidates=scan_result.backcover_photos,
            progress_callback=progress_callback,
        )

        # Write configs
        _cb({"step": "writing_configs"})
        write_global_config(workspace_path, global_cfg)
        write_page_configs(page_map)

        total_pages = len(page_map)
        logger.info(f"Album regenerated with {total_pages} page(s)")

        # #region agent log
        open('/Users/jzabalegui/Coding/Local_PDF_Album_Generator/.cursor/debug-02279c.log','a').write(_json_dbg.dumps({"sessionId":"02279c","hypothesisId":"H1","location":"source_manager.py:regenerate_album","message":"regen SUCCESS","data":{"pages":total_pages,"global_config_exists":(workspace_path/"global_config.yaml").exists()},"timestamp":__import__('time').time()})+'\n')
        # #endregion

        return True

    except Exception as e:
        logger.error(f"Failed to regenerate album: {e}")
        # #region agent log
        open('/Users/jzabalegui/Coding/Local_PDF_Album_Generator/.cursor/debug-02279c.log','a').write(_json_dbg.dumps({"sessionId":"02279c","hypothesisId":"H1","location":"source_manager.py:regenerate_album","message":"regen FAILED","data":{"error":str(e)},"timestamp":__import__('time').time()})+'\n')
        # #endregion
        return False
    finally:
        _regen_running = False
        _regen_lock.release()


def get_event_info(folder_path: Path) -> dict:
    """Get detailed information about an event folder.

    Returns sections grouping top-level photos and any subfolder photos
    (each subfolder becomes its own section). The legacy ``photos`` field is
    a flat list of basenames preserved for callers that don't care about
    grouping.
    """
    try:
        sections = list_event_sections(folder_path)
        flat_photos = [name for s in sections for name in s['photos']]

        return {
            'name': folder_path.name,
            'path': str(folder_path),
            'photo_count': len(flat_photos),
            'photos': flat_photos,
            'sections': sections,
            'completed': read_event_completed(folder_path),
        }

    except Exception as e:
        logger.error(f"Failed to get event info: {e}")
        return {}
