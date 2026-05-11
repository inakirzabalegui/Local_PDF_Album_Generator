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
from src.editor.trash import move_to_trash, TrashToken

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
    temp_dir = None
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
        
        # Remap photo_captions in page_config.yaml to canonical names
        config_path = page_folder / "page_config.yaml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            
            old_captions = data.get('photo_captions', {})
            new_captions = {}
            
            for i, original_name in enumerate(new_order):
                ext = Path(original_name).suffix
                new_name = f"img_{i+1:03d}{ext}"
                if original_name in old_captions:
                    new_captions[new_name] = old_captions[original_name]
            
            data['photo_captions'] = new_captions
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        
        # Clean up temp directory
        temp_dir.rmdir()
        
        logger.info(f"Reordered {len(new_order)} photos in {page_folder.name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to reorder photos: {e}")
        # Cleanup on error
        if temp_dir is not None and temp_dir.exists():
            for f in temp_dir.iterdir():
                shutil.move(str(f), str(page_folder / f.name))
            temp_dir.rmdir()
        return False


def delete_photo(page_folder: Path, filename: str, workspace_root: Path) -> TrashToken | None:
    """Move a photo into the workspace trash and update the page YAML.

    Returns a TrashToken on success so the caller can build an undo entry, or
    None if the photo was not found / the operation failed.
    """
    try:
        photo_path = page_folder / filename
        if not photo_path.exists():
            logger.error(f"Photo not found: {filename}")
            return None

        token = move_to_trash(workspace_root, photo_path)
        logger.info(f"Trashed photo: {filename} (token {token.token_id})")

        # Update page_config.yaml photo_count
        config_path = page_folder / "page_config.yaml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

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

        return token

    except Exception as e:
        logger.error(f"Failed to delete photo: {e}")
        return None


def delete_page(workspace: Path, page_folder: Path) -> dict:
    """Delete an entire page folder and immediately renumber subsequent pages.

    Args:
        workspace: Path to the workspace root
        page_folder: Path to the page folder to delete

    Returns:
        Dict with keys: success (bool), last_in_section (bool), renumbered (int)
    """
    import re

    try:
        if not page_folder.exists():
            logger.error(f"Page folder not found: {page_folder}")
            return {"success": False, "last_in_section": False, "renumbered": 0}

        # Read the deleted page's metadata before removal
        deleted_config_path = page_folder / "page_config.yaml"
        deleted_page_number = None
        deleted_section_id = ""
        if deleted_config_path.exists():
            with open(deleted_config_path, "r", encoding="utf-8") as f:
                deleted_data = yaml.safe_load(f) or {}
            deleted_page_number = deleted_data.get("page_number")
            deleted_section_id = deleted_data.get("section_id", "") or ""

        # Delete the folder
        shutil.rmtree(page_folder)
        logger.info(f"Deleted page folder: {page_folder.name}")

        if deleted_page_number is None:
            return {"success": True, "last_in_section": False, "renumbered": 0}

        # Collect remaining page folders (those with page_config.yaml)
        folder_pattern = re.compile(r"^pagina_(\d+)_(.+)$")
        remaining = []
        for entry in workspace.iterdir():
            if not entry.is_dir():
                continue
            cfg = entry / "page_config.yaml"
            if not cfg.exists():
                continue
            with open(cfg, "r", encoding="utf-8") as f:
                cfg_data = yaml.safe_load(f) or {}
            # Skip cover/backcover pages
            if cfg_data.get("is_cover") or cfg_data.get("is_backcover"):
                continue
            remaining.append((entry, cfg_data))

        # Sort by current page_number
        remaining.sort(key=lambda x: x[1].get("page_number", 0))

        # Determine last_in_section: does any remaining page share the deleted section_id?
        last_in_section = deleted_section_id != "" and not any(
            d.get("section_id", "") == deleted_section_id for _, d in remaining
        )

        # Renumber pages with page_number > deleted_page_number
        renumbered = 0
        for entry, cfg_data in remaining:
            current_num = cfg_data.get("page_number", 0)
            if current_num <= deleted_page_number:
                continue

            new_num = current_num - 1

            # Rename folder: pagina_NN_slug → pagina_(N-1)_slug
            m = folder_pattern.match(entry.name)
            if m:
                slug = m.group(2)
                new_name = f"pagina_{new_num:02d}_{slug}"
                new_path = workspace / new_name
                entry.rename(new_path)
                new_config_path = new_path / "page_config.yaml"
            else:
                # Unexpected name format — update config in-place without renaming
                new_config_path = entry / "page_config.yaml"

            # Update page_number in page_config.yaml
            with open(new_config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data["page_number"] = new_num
            if "photo_captions" not in data:
                data["photo_captions"] = {}
            with open(new_config_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

            renumbered += 1
            logger.info(f"Renumbered page {current_num} → {new_num} ({entry.name})")

        return {"success": True, "last_in_section": last_in_section, "renumbered": renumbered}

    except Exception as e:
        logger.error(f"Failed to delete page: {e}")
        return {"success": False, "last_in_section": False, "renumbered": 0}


def reorder_pages(workspace: Path, ordered_page_ids: list[str]) -> dict:
    """Reorder content pages on disk based on the given ordering.

    Args:
        workspace: Workspace root.
        ordered_page_ids: New ordering of content page folder names, top-to-bottom.
            Must include ALL content pages (excluding portada/contraportada).
            Order must respect section contiguity (validated server-side).

    Returns:
        Dict with success (bool), error (str|None), renamed_pages (list of {old_id, new_id}).
    """
    import re
    import uuid

    try:
        folder_pattern = re.compile(r"^pagina_(\d+)_(.+)$")

        # Collect current content pages
        current_pages = {}
        for entry in workspace.iterdir():
            if not entry.is_dir():
                continue
            cfg_path = entry / "page_config.yaml"
            if not cfg_path.exists():
                continue
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg_data = yaml.safe_load(f) or {}
            if cfg_data.get("is_cover") or cfg_data.get("is_backcover"):
                continue
            current_pages[entry.name] = cfg_data

        # Validate: ordered_page_ids must be a permutation of current content pages
        current_set = set(current_pages.keys())
        ordered_set = set(ordered_page_ids)
        if current_set != ordered_set:
            missing = current_set - ordered_set
            extra = ordered_set - current_set
            msg = []
            if missing:
                msg.append(f"Missing pages: {missing}")
            if extra:
                msg.append(f"Unknown pages: {extra}")
            return {"success": False, "error": "; ".join(msg), "renamed_pages": []}

        # Validate section contiguity
        seen_sections: dict[str, int] = {}  # section_id → last position seen
        prev_section = None
        for pos, page_id in enumerate(ordered_page_ids):
            section_id = current_pages[page_id].get("section_id", "") or ""
            if section_id != prev_section:
                if section_id in seen_sections:
                    return {
                        "success": False,
                        "error": "Cross-section reordering not allowed",
                        "renamed_pages": [],
                    }
                seen_sections[section_id] = pos
                prev_section = section_id

        # Determine starting page_number by finding minimum current page_number
        start_num = min(
            (d.get("page_number", 1) for d in current_pages.values()),
            default=1,
        )

        # Build mapping: page_id → new page_number
        new_numbers = {page_id: start_num + i for i, page_id in enumerate(ordered_page_ids)}

        # Check which pages actually need renaming
        needs_rename = [
            page_id for page_id in ordered_page_ids
            if current_pages[page_id].get("page_number") != new_numbers[page_id]
        ]

        if not needs_rename:
            return {"success": True, "error": None, "renamed_pages": []}

        # Phase 1: rename affected folders to temporary names
        tmp_mapping: dict[str, Path] = {}  # original page_id → tmp path
        uid = uuid.uuid4().hex[:8]
        for page_id in needs_rename:
            original_path = workspace / page_id
            tmp_name = f"_reorder_tmp_{uid}_{page_id}"
            tmp_path = workspace / tmp_name
            original_path.rename(tmp_path)
            tmp_mapping[page_id] = tmp_path
            logger.info(f"Phase-1 rename: {page_id} → {tmp_name}")

        # Phase 2: rename tmp folders to final names and update YAMLs
        renamed_pages = []
        for page_id in needs_rename:
            tmp_path = tmp_mapping[page_id]
            new_num = new_numbers[page_id]

            m = folder_pattern.match(page_id)
            slug = m.group(2) if m else page_id
            new_folder_name = f"pagina_{new_num:02d}_{slug}"
            new_path = workspace / new_folder_name
            tmp_path.rename(new_path)
            logger.info(f"Phase-2 rename: {tmp_path.name} → {new_folder_name}")

            # Update page_number in page_config.yaml
            cfg_path = new_path / "page_config.yaml"
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data["page_number"] = new_num
            if "photo_captions" not in data:
                data["photo_captions"] = {}
            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

            renamed_pages.append({"old_id": page_id, "new_id": new_folder_name})

        return {"success": True, "error": None, "renamed_pages": renamed_pages}

    except Exception as e:
        logger.error(f"Failed to reorder pages: {e}")
        return {"success": False, "error": str(e), "renamed_pages": []}


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


def create_page_after(workspace: Path, after_page_number: int) -> dict:
    """Create a new empty page folder after the specified page number.

    The new folder is given the same page_number as the reference page so that
    the duplicate-resolution logic in reconciler will insert it right after.

    Args:
        workspace: Path to the workspace root
        after_page_number: Page number of the reference page to insert after

    Returns:
        Dict with the new page info, or empty dict on failure
    """
    try:
        global_cfg = read_global_config(workspace)
        pages = read_page_configs(workspace, global_cfg)

        # Find the reference page
        ref_page = next((p for p in pages if p.page_number == after_page_number), None)
        if ref_page is None:
            logger.error(f"Reference page {after_page_number} not found")
            return {}

        # Derive slug from reference folder name
        import re
        match = re.match(r'pagina_\d+_(.*)', ref_page.folder.name)
        slug = match.group(1) if match else "page"

        # Create new folder with same page_number (reconciler handles renumbering)
        new_folder = workspace / f"pagina_{after_page_number:02d}_{slug}_new"
        new_folder.mkdir(exist_ok=True)

        # Build a minimal PageConfig inheriting from the reference page
        from src.workspace.config import PageConfig
        import random as _random
        new_page = PageConfig(
            folder=new_folder,
            page_number=after_page_number,
            photo_count=0,
            layout_seed=_random.randint(0, 2**31),
            section_titles=list(ref_page.section_titles),
            layout_mode=ref_page.layout_mode,
        )
        write_page_configs([new_page])

        logger.info(f"Created new page folder: {new_folder.name}")

        return {
            'folder_name': new_folder.name,
            'page_number': after_page_number,
            'photo_count': 0,
            'images': [],
            'section_titles': list(ref_page.section_titles),
            'layout_mode': ref_page.layout_mode,
        }

    except Exception as e:
        logger.error(f"Failed to create page: {e}")
        return {}


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
            'completed': bool(data.get('completed', False)),
        }
        
    except Exception as e:
        logger.error(f"Failed to get page info: {e}")
        return {}


def move_photos(from_folder: Path, to_folder: Path, filenames: list[str]) -> bool:
    """Move photos from one page to another, renaming as needed.
    
    Args:
        from_folder: Source page folder
        to_folder: Destination page folder
        filenames: List of filenames to move
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get current images in destination folder
        existing_images = sorted(
            p for p in to_folder.iterdir()
            if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
        )
        next_seq = len(existing_images) + 1
        
        # Create temp directory for staging
        temp_dir = from_folder / "_move_tmp"
        temp_dir.mkdir(exist_ok=True)
        
        # Stage photos in temp folder with new names
        staged_files = []
        for filename in filenames:
            src = from_folder / filename
            if not src.exists():
                logger.error(f"File not found: {filename}")
                return False
            
            ext = src.suffix.lower()
            if ext not in VALID_IMAGE_EXTENSIONS:
                ext = ".jpg"
            
            temp_name = f"img_{next_seq:03d}{ext}"
            dst_temp = temp_dir / temp_name
            shutil.move(str(src), str(dst_temp))
            staged_files.append((dst_temp, to_folder / temp_name))
            next_seq += 1
        
        # Move from temp to final destination
        for src_temp, dst_final in staged_files:
            shutil.move(str(src_temp), str(dst_final))
        
        # Clean up temp directory
        temp_dir.rmdir()
        
        # Update photo counts in YAML for both pages
        from_config = from_folder / "page_config.yaml"
        if from_config.exists():
            with open(from_config, 'r', encoding='utf-8') as f:
                from_data = yaml.safe_load(f) or {}
            
            remaining_images = [
                p for p in from_folder.iterdir()
                if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
            ]
            from_data['photo_count'] = len(remaining_images)
            
            # Clean up captions for moved photos
            if 'photo_captions' not in from_data:
                from_data['photo_captions'] = {}
            for fn in filenames:
                from_data['photo_captions'].pop(fn, None)
            
            with open(from_config, 'w', encoding='utf-8') as f:
                yaml.dump(from_data, f, allow_unicode=True, default_flow_style=False)
        
        # Update destination page YAML
        to_config = to_folder / "page_config.yaml"
        if to_config.exists():
            with open(to_config, 'r', encoding='utf-8') as f:
                to_data = yaml.safe_load(f) or {}
            
            all_images = [
                p for p in to_folder.iterdir()
                if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
            ]
            to_data['photo_count'] = len(all_images)
            
            if 'photo_captions' not in to_data:
                to_data['photo_captions'] = {}
            
            with open(to_config, 'w', encoding='utf-8') as f:
                yaml.dump(to_data, f, allow_unicode=True, default_flow_style=False)
        
        logger.info(f"Moved {len(filenames)} photos from {from_folder.name} to {to_folder.name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to move photos: {e}")
        # Cleanup on error
        if temp_dir.exists():
            for f in temp_dir.iterdir():
                shutil.move(str(f), str(from_folder / f.name))
            temp_dir.rmdir()
        return False


def explode_page(workspace: Path, page_id: str) -> dict:
    """Split a page into two: first ceil(n/2) photos stay, rest move to a new page right after.

    The new page inherits section_titles, layout_mode, override_background_color and gets a
    fresh layout_seed. featured_photos, hero_photos, and photo_captions follow their photos.
    The minimum-photos constraint is intentionally ignored (user decides).
    """
    import math
    import random as _random

    page_folder = workspace / page_id
    config_path = page_folder / "page_config.yaml"

    if not page_folder.exists() or not config_path.exists():
        return {'success': False, 'error': 'Página no encontrada'}

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            orig_data = yaml.safe_load(f) or {}

        if orig_data.get('is_cover') or orig_data.get('is_backcover'):
            return {'success': False, 'error': 'No se puede explotar la portada o contraportada'}

        images = sorted(
            p.name for p in page_folder.iterdir()
            if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
        )
        n = len(images)

        if n < 2:
            return {'success': False, 'error': 'Se necesitan al menos 2 fotos para explotar una página'}

        split = math.ceil(n / 2)
        stay = images[:split]
        move = images[split:]

        orig_page_number = orig_data.get('page_number', 1)
        orig_featured = set(orig_data.get('featured_photos') or [])
        orig_hero = set(orig_data.get('hero_photos') or [])
        orig_captions = dict(orig_data.get('photo_captions') or {})
        orig_bg = orig_data.get('override_background_color')

        # Create new page folder (inherits section_titles, layout_mode, new seed)
        new_page_info = create_page_after(workspace, orig_page_number)
        if not new_page_info:
            return {'success': False, 'error': 'Error al crear la nueva página'}

        new_folder = workspace / new_page_info['folder_name']
        new_config_path = new_folder / "page_config.yaml"

        # Propagate override_background_color if set
        if orig_bg is not None:
            with open(new_config_path, 'r', encoding='utf-8') as f:
                new_data = yaml.safe_load(f) or {}
            new_data['override_background_color'] = orig_bg
            with open(new_config_path, 'w', encoding='utf-8') as f:
                yaml.dump(new_data, f, allow_unicode=True, default_flow_style=False)

        # Move photos with staging to avoid name collisions, building rename_map
        temp_dir = page_folder / "_explode_tmp"
        temp_dir.mkdir(exist_ok=True)
        rename_map: dict[str, str] = {}

        try:
            for seq, filename in enumerate(move, start=1):
                src = page_folder / filename
                ext = src.suffix.lower()
                if ext not in VALID_IMAGE_EXTENSIONS:
                    ext = '.jpg'
                new_name = f"img_{seq:03d}{ext}"
                rename_map[filename] = new_name
                shutil.move(str(src), str(temp_dir / new_name))

            for tmp_name in (rename_map[fn] for fn in move):
                shutil.move(str(temp_dir / tmp_name), str(new_folder / tmp_name))

            temp_dir.rmdir()
        except Exception:
            # Restore files from temp back to original page on failure
            for f in temp_dir.iterdir():
                shutil.move(str(f), str(page_folder / f.name))
            temp_dir.rmdir()
            raise

        # Update original page YAML
        moved_set = set(move)
        orig_data['photo_count'] = len(stay)
        orig_data['featured_photos'] = [p for p in (orig_data.get('featured_photos') or []) if p not in moved_set]
        orig_data['hero_photos'] = [p for p in (orig_data.get('hero_photos') or []) if p not in moved_set]
        orig_data['photo_captions'] = {k: v for k, v in orig_captions.items() if k not in moved_set}
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(orig_data, f, allow_unicode=True, default_flow_style=False)

        # Update new page YAML
        with open(new_config_path, 'r', encoding='utf-8') as f:
            new_data = yaml.safe_load(f) or {}
        new_data['photo_count'] = len(move)
        new_data['featured_photos'] = [rename_map[p] for p in move if p in orig_featured]
        new_data['hero_photos'] = [rename_map[p] for p in move if p in orig_hero]
        new_data['photo_captions'] = {rename_map[p]: v for p, v in orig_captions.items() if p in moved_set}
        with open(new_config_path, 'w', encoding='utf-8') as f:
            yaml.dump(new_data, f, allow_unicode=True, default_flow_style=False)

        logger.info(f"Exploded {page_id}: {len(stay)} photos stay, {len(move)} moved to {new_folder.name}")

        return {
            'success': True,
            'original_page': {
                'id': page_id,
                'number': orig_page_number,
                'photo_count': len(stay),
                'layout_mode': orig_data.get('layout_mode', 'mesa_de_luz'),
                'section_titles': orig_data.get('section_titles', []),
            },
            'new_page': {
                'id': new_folder.name,
                'number': new_data.get('page_number', orig_page_number),
                'photo_count': len(move),
                'layout_mode': new_data.get('layout_mode', 'mesa_de_luz'),
                'section_titles': new_data.get('section_titles', []),
            },
        }

    except Exception as e:
        logger.error(f"Failed to explode page {page_id}: {e}")
        return {'success': False, 'error': str(e)}
