"""Source folder management operations for the Source mode."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from src.ingestion.scanner import scan_directory, VALID_EXTENSIONS
from src.ingestion.sorter import sort_photos
from src.utils.naming import prettify_folder_name, folder_name_to_slug
from src.workspace.initializer import create_workspace
from src.workspace.config import write_global_config, write_page_configs, read_global_config

logger = logging.getLogger("album.editor.source")


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
    """List photos in a folder, sorted chronologically by EXIF.
    
    Args:
        folder_path: Path to the folder
        
    Returns:
        List of filenames sorted by EXIF date
    """
    if not folder_path.is_dir():
        return []
    
    # Scan photos in folder
    photos = [
        p for p in folder_path.iterdir()
        if p.is_file() and p.suffix.lower() in VALID_EXTENSIONS
    ]
    
    if not photos:
        return []
    
    # Create PhotoInfo objects for sorting
    from src.ingestion.scanner import PhotoInfo
    
    photo_infos = []
    for p in photos:
        w, h = (1920, 1080)  # Default aspect ratio
        try:
            from PIL import Image
            with Image.open(p) as img:
                w, h = img.size
        except Exception:
            pass
        
        photo_info = PhotoInfo(path=p, width=w, height=h, source_group=folder_path.name)
        photo_infos.append(photo_info)
    
    # Sort by EXIF date
    sorted_infos = sort_photos(photo_infos)
    
    return [p.path.name for p in sorted_infos]


def delete_photo(folder_path: Path, filename: str) -> bool:
    """Delete a photo from the folder.
    
    Args:
        folder_path: Path to the folder
        filename: Name of the photo file to delete
        
    Returns:
        True if successful, False otherwise
    """
    try:
        photo_path = folder_path / filename
        if not photo_path.exists():
            logger.error(f"Photo not found: {filename}")
            return False
        
        photo_path.unlink()
        logger.info(f"Deleted photo: {filename}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete photo: {e}")
        return False


def delete_folder(source_path: Path, folder_name: str) -> bool:
    """Delete an event folder.
    
    Args:
        source_path: Path to the source directory
        folder_name: Name of the folder to delete
        
    Returns:
        True if successful, False otherwise
    """
    try:
        folder_path = source_path / folder_name
        if not folder_path.exists():
            logger.error(f"Folder not found: {folder_name}")
            return False
        
        shutil.rmtree(folder_path)
        logger.info(f"Deleted folder: {folder_name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete folder: {e}")
        return False


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
        
        # Calculate prefix from new folder name
        # Extract the part after YYYYMMDD_ if present
        prefix_name = new_name
        if len(prefix_name) >= 8 and prefix_name[:8].isdigit():
            prefix_name = prefix_name[9:] if len(prefix_name) > 9 and prefix_name[8] == '_' else prefix_name[8:]
        
        # Convert to CamelCase slug (e.g., "Comida despedida Js" -> "ComidaDespedidaJs")
        clean_name = prettify_folder_name(prefix_name)
        prefix = ''.join(word.capitalize() for word in clean_name.split())
        
        # Stage photos with new names
        temp_dir = new_path / ".rename_tmp"
        temp_dir.mkdir(exist_ok=True)
        
        staged_files = []
        for seq, filename in enumerate(photos, 1):
            src = new_path / filename
            ext = src.suffix.lower()
            if ext not in VALID_EXTENSIONS:
                ext = ".jpg"
            
            temp_name = f"{prefix}_{seq:03d}{ext}"
            dst_temp = temp_dir / temp_name
            shutil.move(str(src), str(dst_temp))
            staged_files.append(dst_temp)
        
        # Move from temp to final
        for src_temp in staged_files:
            dst_final = new_path / src_temp.name
            shutil.move(str(src_temp), str(dst_final))
        
        temp_dir.rmdir()
        
        logger.info(f"Renamed {len(photos)} photos in {new_name} with prefix {prefix}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to rename folder and photos: {e}")
        # Try to cleanup temp dir if it exists
        try:
            new_path = source_path / new_name
            temp_dir = new_path / ".rename_tmp"
            if temp_dir.exists():
                for f in temp_dir.iterdir():
                    shutil.move(str(f), str(new_path / f.name))
                temp_dir.rmdir()
        except Exception:
            pass
        return False


def regenerate_album(source_path: Path, workspace_path: Path) -> bool:
    """Regenerate the album workspace from source photos.
    
    If workspace exists, it will be deleted and recreated.
    
    Args:
        source_path: Path to the source directory
        workspace_path: Path to the workspace directory
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Regenerating album: {workspace_path}")
        
        # Delete existing workspace if it exists
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
            logger.info(f"Deleted existing workspace")
        
        # Scan source directory
        logger.info(f"Scanning source: {source_path}")
        scan_result = scan_directory(source_path)
        
        if not scan_result.photos:
            logger.warning("No photos found in source")
            return False
        
        # Sort photos
        logger.info(f"Sorting {len(scan_result.photos)} photos")
        sorted_photos = sort_photos(scan_result.photos)
        
        # Create workspace
        logger.info(f"Creating workspace: {workspace_path}")
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        global_cfg, page_map = create_workspace(
            sorted_photos,
            workspace_path,
            source_dir_name=source_path.name,
            cover_candidates=scan_result.cover_photos,
            backcover_candidates=scan_result.backcover_photos,
        )
        
        # Write configs
        write_global_config(workspace_path, global_cfg)
        write_page_configs(page_map)
        
        total_pages = len(page_map)
        logger.info(f"Album regenerated with {total_pages} page(s)")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to regenerate album: {e}")
        return False


def get_event_info(folder_path: Path) -> dict:
    """Get detailed information about an event folder.
    
    Args:
        folder_path: Path to the event folder
        
    Returns:
        Dictionary with event information
    """
    try:
        photos = list_photos(folder_path)
        
        return {
            'name': folder_path.name,
            'path': str(folder_path),
            'photo_count': len(photos),
            'photos': photos,
        }
        
    except Exception as e:
        logger.error(f"Failed to get event info: {e}")
        return {}
