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

from src.utils.naming import folder_name_to_slug, prettify_folder_name
from src.workspace.config import (
    GlobalConfig,
    PageConfig,
    VALID_IMAGE_EXTENSIONS,
    write_page_configs,
)
from src.workspace.manifest import (
    PageManifest,
    PhotoManifestEntry,
    read_page_manifest,
    write_page_manifest,
)


def _sub_group_from_source_path(source_path: str) -> str:
    """Extract sub_group (second segment of POSIX rel path), or "" for top-level."""
    if not source_path:
        return ""
    parts = source_path.split("/")
    # parts[0] = source_group, parts[1] = sub_group (if photo lives in subfolder)
    if len(parts) >= 3:
        return parts[1]
    return ""


def _rebuild_titles(top_title: str, sub_group_ids: list[str]) -> list[str]:
    titles: list[str] = []
    if top_title:
        titles.append(top_title)
    if sub_group_ids:
        titles.append(" / ".join(prettify_folder_name(s) for s in sub_group_ids))
    return titles

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
        # Only the non-completed (free) slice participates in reconciliation.
        free_pages = [p for p in group_pages if not p.completed]
        counts = [len(p.image_files()) for p in free_pages]
        # An empty free page in a section that has photos elsewhere needs work.
        if 0 in counts:
            needs_work = True
            break
        total_free = sum(counts)
        if free_pages:
            expected = max(1, math.ceil(total_free / target_per_page)) if total_free else 0
            if expected != len(free_pages) and total_free > 0:
                needs_work = True
                break
            if total_free == 0 and len(free_pages) > 1:
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
    """Reconcile a single section group. Returns surviving PageConfigs.

    Pages with `completed: true` are immutable: their current photo set is
    preserved verbatim (photos whose sources were deleted have already been
    removed from disk and will simply not appear in `image_files()`).
    Only non-completed pages absorb redistribution / new photos.
    """
    section_label = group_pages[0].section_titles[0] if group_pages[0].section_titles else "unknown"

    completed_pages = [p for p in group_pages if p.completed]
    free_pages = [p for p in group_pages if not p.completed]

    # Warn about empty completed pages (all source photos deleted).
    for p in completed_pages:
        if not p.image_files():
            logger.warning(
                f"Page {p.page_number} (completed) is now empty after source "
                f"deletions; leaving as an empty completed page. The user must "
                f"resolve it manually."
            )

    # Warn about completed pages that fall outside min/max.
    for p in completed_pages:
        c = len(p.image_files())
        if c and (c < cfg.photos_per_page_min or c > cfg.photos_per_page_max):
            logger.warning(
                f"Page {p.page_number} (completed) has {c} photos "
                f"(outside {cfg.photos_per_page_min}-{cfg.photos_per_page_max}); "
                f"leaving as-is per user lock."
            )

    # Gather photos only from the free (non-completed) pages.
    all_photos: list[Path] = []
    photo_meta: dict[str, tuple[str, PhotoManifestEntry | None]] = {}
    for page in free_pages:
        page_manifest = read_page_manifest(page.folder)
        for img_path in page.image_files():
            all_photos.append(img_path)
            entry = None
            sub_group = ""
            if page_manifest is not None:
                entry = page_manifest.photos.get(img_path.name)
                if entry is not None:
                    sub_group = _sub_group_from_source_path(entry.source_path)
            photo_meta[str(img_path)] = (sub_group, entry)

    logger.debug(
        f"Reconciling section '{section_label}': "
        f"{len(all_photos)} free photos across {len(free_pages)} non-completed pages "
        f"({len(completed_pages)} completed pages frozen)"
    )

    # Section emptied of free photos AND no completed pages: drop everything.
    if not all_photos and not completed_pages:
        for page in group_pages:
            if page.folder.exists():
                shutil.rmtree(page.folder)
                logger.debug(f"  Removed empty folder: {page.folder.name}")
        return []

    # No free photos but completed pages exist: drop empty free folders, keep frozen.
    if not all_photos:
        for page in free_pages:
            if page.folder.exists():
                shutil.rmtree(page.folder)
                logger.debug(f"  Removed empty free folder: {page.folder.name}")
        return list(completed_pages)

    num_pages_needed = max(1, math.ceil(len(all_photos) / target_per_page))

    counts = [len(p.image_files()) for p in free_pages]
    if free_pages and 0 not in counts and num_pages_needed == len(free_pages):
        # Free slice already balanced. Return free + completed unchanged.
        return list(group_pages)

    # If no free pages exist but new photos do, we must create overflow pages.
    if not free_pages:
        # All section pages are completed; the only way photos end up in
        # all_photos is impossible here (we only collected from free pages).
        # Defensive: return as-is.
        return list(completed_pages)

    logger.info(
        f"  Redistributing '{section_label}' (free slice): "
        f"{len(all_photos)} photos → {num_pages_needed} pages "
        f"({len(completed_pages)} completed pages untouched)"
    )

    # The redistribution loop below operates on `group_pages` aliased to free_pages
    # so the existing rewrite logic keeps working.
    group_pages = free_pages

    chunk_sizes = _even_chunks(len(all_photos), num_pages_needed)

    # Move all photos to a temp staging directory, carrying per-photo metadata.
    temp_dir = workspace / "_reconcile_staging"
    temp_dir.mkdir(exist_ok=True)
    staged: list[Path] = []
    staged_meta: list[tuple[str, PhotoManifestEntry | None]] = []
    for photo in all_photos:
        dst = temp_dir / f"{len(staged):05d}{photo.suffix.lower()}"
        shutil.move(str(photo), str(dst))
        staged.append(dst)
        staged_meta.append(photo_meta.get(str(photo), ("", None)))

    # Build page configs for each chunk, reusing existing settings
    result_pages: list[PageConfig] = []
    photo_idx = 0

    for chunk_idx, size in enumerate(chunk_sizes):
        chunk = staged[photo_idx : photo_idx + size]
        chunk_meta = staged_meta[photo_idx : photo_idx + size]
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
                section_id=ref.section_id,
            )

        # Clear any leftover images in the folder
        for old in page.image_files():
            old.unlink()

        # Place chunk photos and rebuild manifest entries
        new_manifest_photos: dict[str, PhotoManifestEntry] = {}
        page_sub_groups: list[str] = []
        for seq, (photo, (sub_group, entry)) in enumerate(zip(chunk, chunk_meta), 1):
            ext = photo.suffix.lower()
            if ext not in (".jpg", ".jpeg"):
                ext = ".jpg"
            img_name = f"img_{seq:03d}{ext}"
            dst = page.folder / img_name
            shutil.move(str(photo), str(dst))
            if entry is not None:
                new_manifest_photos[img_name] = PhotoManifestEntry(
                    image_name=img_name,
                    source_path=entry.source_path,
                    source_mtime=entry.source_mtime,
                    sha1=entry.sha1,
                )
            if sub_group and sub_group not in page_sub_groups:
                page_sub_groups.append(sub_group)

        page.photo_count = size
        page.sub_group_ids = page_sub_groups
        top_title = page.section_titles[0] if page.section_titles else ""
        page.section_titles = _rebuild_titles(top_title, page_sub_groups)

        # Persist refreshed manifest if we have any entries to write
        if new_manifest_photos:
            write_page_manifest(PageManifest(
                folder=page.folder,
                section_id=page.section_id,
                photos=new_manifest_photos,
            ))

        result_pages.append(page)

    # Remove excess page folders
    for excess in group_pages[len(chunk_sizes) :]:
        if excess.folder.exists():
            shutil.rmtree(excess.folder)
            logger.debug(f"  Removed excess folder: {excess.folder.name}")

    # Clean staging
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    # Include the frozen completed pages alongside the redistributed free pages.
    return result_pages + list(completed_pages)


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
