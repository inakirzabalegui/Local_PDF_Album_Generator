"""Pre-render workspace reconciliation.

Detects deletions (folders or photos) since --init and redistributes
photos within each section group, physically renaming folders and
updating YAML configs before PDF generation.
"""

from __future__ import annotations

import logging
import math
import shutil
from pathlib import Path

from src.utils.naming import folder_name_to_slug
from src.workspace.config import (
    GlobalConfig,
    PageConfig,
    VALID_IMAGE_EXTENSIONS,
    write_page_configs,
)

logger = logging.getLogger("album")


def reconcile(
    pages: list[PageConfig],
    cfg: GlobalConfig,
    workspace: Path,
) -> list[PageConfig]:
    """Detect deletions since init and redistribute photos before rendering.

    1. Groups content pages by section (section_titles).
    2. Removes physically empty page folders.
    3. Redistributes ALL photos of a modified section evenly.
    4. Renumbers pages sequentially and renames folders.
    5. Writes updated YAML configs.

    Cover/backcover pages are never touched.
    Layout mode and seed are preserved from existing pages.
    """
    content = [p for p in pages if not p.is_cover and not p.is_backcover]
    special = [p for p in pages if p.is_cover or p.is_backcover]

    if not content:
        return pages

    # Check for page number gaps (deleted folders)
    content.sort(key=lambda p: p.page_number)

    # Resolve duplicate page numbers (manually created folders)
    content = _resolve_duplicates(content, workspace)

    expected = list(range(1, len(content) + 1))
    actual = [p.page_number for p in content]
    
    if actual != expected:
        missing = set(expected) - set(actual)
        if missing:
            logger.info(
                f"Detected deleted page(s): {sorted(missing)}. "
                f"Renumbering {len(content)} pages sequentially (1..{len(content)})"
            )
        else:
            logger.info(
                f"Detected page number gaps. "
                f"Renumbering from {actual[0]}..{actual[-1]} to 1..{len(content)}"
            )
        
        for new_num, page in enumerate(content, start=1):
            page.page_number = new_num
        
        _rename_folders(content, workspace)
        write_page_configs(content)
        logger.info("Page renumbering complete")

    groups = _group_by_section(content)

    # Quick check: does any section need work?
    target_per_page = (cfg.photos_per_page_min + cfg.photos_per_page_max) // 2
    needs_work = False
    for group_pages in groups.values():
        counts = [len(p.image_files()) for p in group_pages]
        if 0 in counts:
            needs_work = True
            break
        total = sum(counts)
        expected = max(1, math.ceil(total / target_per_page))
        if expected != len(group_pages):
            needs_work = True
            break

    if not needs_work:
        logger.info("No deletions detected — workspace is consistent.")
        return pages

    # Process each section
    surviving_pages: list[PageConfig] = []
    for section_key, group_pages in groups.items():
        result = _reconcile_section(group_pages, cfg, workspace, target_per_page)
        surviving_pages.extend(result)

    # Renumber pages sequentially (cover is page 0)
    surviving_pages.sort(key=lambda p: p.page_number)
    for new_num, page in enumerate(surviving_pages, start=1):
        page.page_number = new_num

    # Rename folders to reflect new numbering
    _rename_folders(surviving_pages, workspace)

    # Write updated YAMLs
    write_page_configs(surviving_pages)
    logger.info(f"Reconciliation complete: {len(surviving_pages)} content pages")

    all_pages = special + surviving_pages
    all_pages.sort(key=lambda p: p.page_number)
    return all_pages


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_creation_time(folder: Path) -> float:
    """Get folder creation time. Falls back to mtime if birthtime unavailable."""
    stat = folder.stat()
    return getattr(stat, 'st_birthtime', stat.st_mtime)


def _resolve_duplicates(
    content: list[PageConfig],
    workspace: Path,
) -> list[PageConfig]:
    """Detect duplicate page_numbers and resolve by insertion order.

    When two folders have the same page_number, the newer one (by filesystem
    creation date) is inserted after the original. All pages are renumbered.
    """
    # Group by page_number
    by_number: dict[int, list[PageConfig]] = {}
    for p in content:
        by_number.setdefault(p.page_number, []).append(p)

    # Check if any duplicates exist
    has_duplicates = any(len(pages) > 1 for pages in by_number.values())
    if not has_duplicates:
        return content

    # For each duplicate set, sort by folder creation time
    for num, pages in by_number.items():
        if len(pages) > 1:
            pages.sort(key=lambda p: _get_creation_time(p.folder))
            logger.info(
                f"Detected {len(pages)} folders with page_number {num}. "
                f"Ordering by creation time."
            )

    # Build ordered list
    result: list[PageConfig] = []
    for num in sorted(by_number.keys()):
        result.extend(by_number[num])

    # Renumber sequentially
    for new_num, page in enumerate(result, start=1):
        page.page_number = new_num

    # Rename folders and write configs
    _rename_folders(result, workspace)
    write_page_configs(result)
    logger.info(f"Duplicate resolution complete: renumbered {len(result)} pages")

    return result


def _group_by_section(pages: list[PageConfig]) -> dict[tuple, list[PageConfig]]:
    """Group pages by section_titles, preserving insertion order."""
    groups: dict[tuple, list[PageConfig]] = {}
    for page in pages:
        key = tuple(page.section_titles) if page.section_titles else ()
        groups.setdefault(key, []).append(page)
    for group_pages in groups.values():
        group_pages.sort(key=lambda p: p.page_number)
    return groups


def _reconcile_section(
    group_pages: list[PageConfig],
    cfg: GlobalConfig,
    workspace: Path,
    target_per_page: int,
) -> list[PageConfig]:
    """Reconcile a single section group. Returns surviving PageConfigs."""
    all_photos: list[Path] = []
    for page in group_pages:
        all_photos.extend(page.image_files())

    section_label = group_pages[0].section_titles[0] if group_pages[0].section_titles else "unknown"
    logger.debug(
        f"Reconciling section '{section_label}': "
        f"{len(all_photos)} photos across {len(group_pages)} pages"
    )

    if not all_photos:
        for page in group_pages:
            if page.folder.exists():
                shutil.rmtree(page.folder)
                logger.debug(f"  Removed empty folder: {page.folder.name}")
        return []

    num_pages_needed = max(1, math.ceil(len(all_photos) / target_per_page))

    counts = [len(p.image_files()) for p in group_pages]
    if 0 not in counts and num_pages_needed == len(group_pages):
        return group_pages

    logger.info(
        f"  Redistributing '{section_label}': "
        f"{len(all_photos)} photos → {num_pages_needed} pages"
    )

    chunk_sizes = _even_chunks(len(all_photos), num_pages_needed)

    # Move all photos to a temp staging directory
    temp_dir = workspace / "_reconcile_staging"
    temp_dir.mkdir(exist_ok=True)
    staged: list[Path] = []
    for photo in all_photos:
        dst = temp_dir / f"{len(staged):05d}{photo.suffix.lower()}"
        shutil.move(str(photo), str(dst))
        staged.append(dst)

    # Build page configs for each chunk, reusing existing settings
    result_pages: list[PageConfig] = []
    photo_idx = 0

    for chunk_idx, size in enumerate(chunk_sizes):
        chunk = staged[photo_idx : photo_idx + size]
        photo_idx += size

        if chunk_idx < len(group_pages):
            page = group_pages[chunk_idx]
        else:
            ref = group_pages[0]
            new_folder = workspace / f"_new_page_{chunk_idx}"
            new_folder.mkdir(exist_ok=True)
            page = PageConfig(
                folder=new_folder,
                page_number=ref.page_number + chunk_idx,
                photo_count=0,
                layout_seed=ref.layout_seed + chunk_idx * 7,
                section_titles=list(ref.section_titles),
                layout_mode=ref.layout_mode,
            )

        # Clear any leftover images in the folder
        for old in page.image_files():
            old.unlink()

        # Place chunk photos
        for seq, photo in enumerate(chunk, 1):
            ext = photo.suffix.lower()
            if ext not in (".jpg", ".jpeg"):
                ext = ".jpg"
            dst = page.folder / f"img_{seq:03d}{ext}"
            shutil.move(str(photo), str(dst))

        page.photo_count = size
        result_pages.append(page)

    # Remove excess page folders
    for excess in group_pages[len(chunk_sizes) :]:
        if excess.folder.exists():
            shutil.rmtree(excess.folder)
            logger.debug(f"  Removed excess folder: {excess.folder.name}")

    # Clean staging
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    return result_pages


def _even_chunks(total: int, num_pages: int) -> list[int]:
    """Distribute *total* items across *num_pages* as evenly as possible."""
    base = total // num_pages
    extra = total % num_pages
    return [base + (1 if i < extra else 0) for i in range(num_pages)]


def _rename_folders(pages: list[PageConfig], workspace: Path) -> None:
    """Rename page folders to match sequential numbering (two-pass to avoid conflicts)."""
    renames: list[tuple[PageConfig, Path]] = []

    for page in pages:
        title = ""
        if page.section_titles:
            parts = page.section_titles[0].split(" - ", 1)
            title = parts[1] if len(parts) > 1 else parts[0]
        slug = folder_name_to_slug(title) if title else "page"
        target = workspace / f"pagina_{page.page_number:02d}_{slug}"

        if page.folder != target:
            renames.append((page, target))

    if not renames:
        return

    # Pass 1 — move to temp names
    temps: list[tuple[PageConfig, Path, Path]] = []
    for page, target in renames:
        tmp = workspace / f"_tmp_{page.page_number:04d}"
        if page.folder.exists():
            shutil.move(str(page.folder), str(tmp))
        temps.append((page, tmp, target))

    # Pass 2 — move to final names
    for page, tmp, target in temps:
        if tmp.exists():
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(tmp), str(target))
        page.folder = target
