"""Workspace management operations for the interactive editor."""

from __future__ import annotations

import shutil
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from src.workspace.config import GlobalConfig, PageConfig

from src.workspace.config import (
    VALID_IMAGE_EXTENSIONS,
    read_global_config,
    read_page_configs,
    write_page_configs,
)
from src.render.pdf_generator import generate_single_page_pdf

logger = logging.getLogger("album.editor")


def load_workspace(workspace_path: Path) -> tuple[GlobalConfig, list[PageConfig]]:
    """Load global config and all page configs from workspace.
    
    Returns:
        Tuple of (global_config, list_of_page_configs)
    """
    global_cfg = read_global_config(workspace_path)
    pages = read_page_configs(workspace_path, global_cfg)
    return global_cfg, pages


def reorder_photos(page_folder: Path, new_order: list[str]) -> bool:
    """Reorder photos by renaming files to match new sequence.
    
    Args:
        page_folder: Path to the page folder
        new_order: List of current filenames in desired order
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Validate all files exist
        for filename in new_order:
            if not (page_folder / filename).exists():
                logger.error(f"File not found: {filename}")
                return False
        
        # Create temp directory for staging
        temp_dir = page_folder / "_reorder_tmp"
        temp_dir.mkdir(exist_ok=True)
        
        # Move files to temp with new names
        staged_files = []
        for seq, filename in enumerate(new_order, 1):
            src = page_folder / filename
            ext = src.suffix.lower()
            if ext not in VALID_IMAGE_EXTENSIONS:
                ext = ".jpg"
            
            temp_name = f"img_{seq:03d}{ext}"
            dst = temp_dir / temp_name
            shutil.move(str(src), str(dst))
            staged_files.append(dst)
        
        # Move back from temp to final location
        for temp_file in staged_files:
            final_dst = page_folder / temp_file.name
            shutil.move(str(temp_file), str(final_dst))
        
        # Clean up temp directory
        temp_dir.rmdir()
        
        logger.info(f"Reordered {len(new_order)} photos in {page_folder.name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to reorder photos: {e}")
        # Cleanup on error
        if temp_dir.exists():
            for f in temp_dir.iterdir():
                shutil.move(str(f), str(page_folder / f.name))
            temp_dir.rmdir()
        return False


def delete_photo(page_folder: Path, filename: str) -> bool:
    """Delete a photo from the page and update YAML.
    
    Args:
        page_folder: Path to the page folder
        filename: Name of the photo file to delete
        
    Returns:
        True if successful, False otherwise
    """
    try:
        photo_path = page_folder / filename
        if not photo_path.exists():
            logger.error(f"Photo not found: {filename}")
            return False
        
        # Delete the photo
        photo_path.unlink()
        logger.info(f"Deleted photo: {filename}")
        
        # Update page_config.yaml photo_count
        config_path = page_folder / "page_config.yaml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            
            # Get current image count
            remaining_images = [
                p for p in page_folder.iterdir()
                if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
            ]
            data['photo_count'] = len(remaining_images)
            
            # Ensure photo_captions exists so it's not lost on rewrite
            if 'photo_captions' not in data:
                data['photo_captions'] = {}
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete photo: {e}")
        return False


def delete_page(workspace: Path, page_folder: Path) -> bool:
    """Delete an entire page folder.
    
    Note: This marks the page for deletion. Reconciliation will handle
    renumbering when --render is next called.
    
    Args:
        workspace: Path to the workspace root
        page_folder: Path to the page folder to delete
        
    Returns:
        True if successful, False otherwise
    """
    try:
        if not page_folder.exists():
            logger.error(f"Page folder not found: {page_folder}")
            return False
        
        # Delete the entire folder
        shutil.rmtree(page_folder)
        logger.info(f"Deleted page folder: {page_folder.name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete page: {e}")
        return False


def update_page_title(page_folder: Path, new_titles: list[str]) -> bool:
    """Update the section_titles in page_config.yaml.
    
    Args:
        page_folder: Path to the page folder
        new_titles: New list of section titles
        
    Returns:
        True if successful, False otherwise
    """
    try:
        config_path = page_folder / "page_config.yaml"
        if not config_path.exists():
            logger.error(f"Config not found: {config_path}")
            return False
        
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        
        data['section_titles'] = new_titles
        
        # Ensure photo_captions exists so it's not lost on rewrite
        if 'photo_captions' not in data:
            data['photo_captions'] = {}
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        
        logger.info(f"Updated titles for {page_folder.name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update title: {e}")
        return False


def generate_preview(page_folder: Path, global_cfg: GlobalConfig) -> Path | None:
    """Generate preview PDF for the current page state.
    
    Args:
        page_folder: Path to the page folder
        global_cfg: Global configuration
        
    Returns:
        Path to the generated preview PDF, or None if failed
    """
    try:
        # Load page config
        config_path = page_folder / "page_config.yaml"
        if not config_path.exists():
            logger.error(f"Config not found: {config_path}")
            return None
        
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        
        # Get actual images
        actual_images = sorted(
            p for p in page_folder.iterdir()
            if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
        )
        
        # Create PageConfig object
        from src.workspace.config import PageConfig
        import random
        
        page_cfg = PageConfig(
            folder=page_folder,
            page_number=data.get("page_number", 0),
            photo_count=len(actual_images),
            layout_seed=data.get("layout_seed", random.randint(0, 2**31)),
            override_background_color=data.get("override_background_color"),
            is_cover=data.get("is_cover", False),
            is_backcover=data.get("is_backcover", False),
            section_titles=data.get("section_titles", []),
            layout_mode=data.get("layout_mode", "mesa_de_luz"),
            featured_photos=data.get("featured_photos", []),
            hero_photos=data.get("hero_photos", []),
        )
        
        # Generate PDF
        output_path = generate_single_page_pdf(page_cfg, global_cfg)
        logger.info(f"Generated preview: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Failed to generate preview: {e}")
        return None


def update_photo_caption(page_folder: Path, filename: str, caption: str) -> bool:
    """Update caption for a specific photo.
    
    Args:
        page_folder: Path to the page folder
        filename: Name of the photo file
        caption: New caption text (empty string to remove)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        config_path = page_folder / "page_config.yaml"
        if not config_path.exists():
            logger.error(f"Config not found: {config_path}")
            return False
        
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        
        if 'photo_captions' not in data:
            data['photo_captions'] = {}
        
        if caption.strip():
            data['photo_captions'][filename] = caption.strip()
        else:
            # Remove caption if empty
            data['photo_captions'].pop(filename, None)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        
        logger.info(f"Updated caption for {filename} in {page_folder.name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update caption: {e}")
        return False


def get_page_info(page_folder: Path) -> dict:
    """Get detailed information about a page.
    
    Args:
        page_folder: Path to the page folder
        
    Returns:
        Dictionary with page information
    """
    try:
        config_path = page_folder / "page_config.yaml"
        if not config_path.exists():
            return {}
        
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        
        # Get images
        images = sorted(
            p.name for p in page_folder.iterdir()
            if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
        )
        
        return {
            'folder_name': page_folder.name,
            'page_number': data.get('page_number', 0),
            'photo_count': len(images),
            'images': images,
            'section_titles': data.get('section_titles', []),
            'layout_mode': data.get('layout_mode', 'mesa_de_luz'),
            'is_cover': data.get('is_cover', False),
            'is_backcover': data.get('is_backcover', False),
            'photo_captions': data.get('photo_captions', {}),
        }
        
    except Exception as e:
        logger.error(f"Failed to get page info: {e}")
        return {}
