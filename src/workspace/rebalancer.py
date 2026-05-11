"""Cascade rebalancing of page folders when photo counts are out of range.

Pages marked `completed: true` are treated as immutable: no photos enter,
no photos leave, and the page itself is never split or merged. When a
cascade would have to move photos through a completed page, the chain is
broken and an overflow page is created within the same section.
"""

from __future__ import annotations

import logging
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


def rebalance(
    pages: list[PageConfig],
    cfg: GlobalConfig,
    workspace: Path,
) -> list[PageConfig]:
    """Rebalance photos across content pages so every page has min..max photos.

    Cover and backcover pages are excluded from rebalancing.
    Rebalancing only occurs within pages of the same group (same section_titles).
    Pages with `completed: true` are immutable and skipped as both source and
    destination during the cascade. When a completed page blocks an overflow,
    a new overflow page is created right after it.
    Returns the updated (and potentially rewritten) page list.
    """
    content = [p for p in pages if not p.is_cover and not p.is_backcover]
    special = [p for p in pages if p.is_cover or p.is_backcover]

    if not content:
        return pages

    groups = _group_by_section(content)
    changed = False
    new_pages: list[PageConfig] = []

    for group_pages in groups.values():
        if len(group_pages) < 1:
            continue

        changed_fwd, created_fwd = _cascade_forward(group_pages, cfg, workspace)
        # Merge any freshly created pages into the in-memory group so backward
        # cascade sees them too.
        if created_fwd:
            group_pages.extend(created_fwd)
            group_pages.sort(key=lambda p: p.page_number)
            new_pages.extend(created_fwd)

        changed_bwd = _cascade_backward(group_pages, cfg)
        changed = changed or changed_fwd or changed_bwd or bool(created_fwd)

        # Warn about completed pages that are out of range.
        for p in group_pages:
            if not p.completed:
                continue
            count = len(p.image_files())
            if count < cfg.photos_per_page_min or count > cfg.photos_per_page_max:
                logger.warning(
                    f"Page {p.page_number} is marked completed and has {count} "
                    f"photos (outside {cfg.photos_per_page_min}-{cfg.photos_per_page_max}); "
                    f"leaving as-is per user lock."
                )

    if new_pages:
        content.extend(new_pages)
        content.sort(key=lambda p: p.page_number)
        # Renumber sequentially after insertions.
        for new_num, page in enumerate(content, start=1):
            page.page_number = new_num
        _rename_folders(content, workspace)

    if changed:
        for pc in content:
            pc.photo_count = len(pc.image_files())
        write_page_configs(content)
        logger.info("Páginas rebalanceadas y YAMLs actualizados.")
    else:
        logger.info("No se requieren cambios en el rebalanceo.")

    all_pages = special + content
    all_pages.sort(key=lambda p: p.page_number)
    return all_pages


def _group_by_section(pages: list[PageConfig]) -> dict[str, list[PageConfig]]:
    """Group pages by their section_titles to prevent cross-group rebalancing."""
    groups: dict[str, list[PageConfig]] = {}
    for page in pages:
        key = tuple(page.section_titles) if page.section_titles else ()
        key_str = str(key)
        if key_str not in groups:
            groups[key_str] = []
        groups[key_str].append(page)

    for group_pages in groups.values():
        group_pages.sort(key=lambda p: p.page_number)

    return groups


def _next_open_index(
    pages: list[PageConfig], start: int
) -> int | None:
    """Return the index >= start of the next non-completed page, or None."""
    for j in range(start, len(pages)):
        if not pages[j].completed:
            return j
    return None


def _cascade_forward(
    pages: list[PageConfig], cfg: GlobalConfig, workspace: Path
) -> tuple[bool, list[PageConfig]]:
    """Push excess photos forward. Skip completed pages as both source and destination.

    If overflow can't land anywhere downstream, create a new overflow page.
    Returns (changed, new_pages_created).
    """
    changed = False
    created: list[PageConfig] = []
    i = 0
    while i < len(pages):
        if pages[i].completed:
            i += 1
            continue
        images = pages[i].image_files()
        if len(images) <= cfg.photos_per_page_max:
            i += 1
            continue

        excess = images[cfg.photos_per_page_max :]
        # Find next non-completed page downstream.
        dst_idx = _next_open_index(pages, i + 1)

        # Log skips for any completed pages between i and dst_idx.
        end = dst_idx if dst_idx is not None else len(pages)
        for k in range(i + 1, end):
            if pages[k].completed:
                logger.info(
                    f"Page {pages[k].page_number} (completed) skipped during rebalance"
                )

        if dst_idx is None:
            # No downstream non-completed page: create one after the last page.
            new_page = _create_overflow_page(pages[i], pages, workspace)
            pages.append(new_page)
            created.append(new_page)
            dst_idx = len(pages) - 1

        for img in excess:
            _move_image(img, pages[dst_idx].folder)
        changed = True
        i += 1

    return changed, created


def _cascade_backward(pages: list[PageConfig], cfg: GlobalConfig) -> bool:
    """Pull photos from a later non-completed page into page[i] if below min.

    Skips completed pages as both source and destination. If page[i] is
    completed, do nothing for it. If page[i] is below min and no
    non-completed donor exists downstream, leave page[i] short and warn.
    """
    changed = False
    for i in range(len(pages)):
        if pages[i].completed:
            continue
        images = pages[i].image_files()
        deficit = cfg.photos_per_page_min - len(images)
        if deficit <= 0:
            continue

        # Find the next non-completed donor downstream that has photos to spare.
        donor_idx = None
        for j in range(i + 1, len(pages)):
            if pages[j].completed:
                logger.info(
                    f"Page {pages[j].page_number} (completed) skipped during rebalance"
                )
                continue
            donor_idx = j
            break

        if donor_idx is None:
            logger.warning(
                f"Page {pages[i].page_number} is below the {cfg.photos_per_page_min}-photo "
                f"minimum and no eligible (non-completed) donor page is available; "
                f"leaving it short."
            )
            continue

        next_images = pages[donor_idx].image_files()
        to_pull = next_images[:deficit]
        if not to_pull:
            continue
        for img in to_pull:
            _move_image(img, pages[i].folder)
        changed = True

    return changed


def _create_overflow_page(
    ref: PageConfig, pages: list[PageConfig], workspace: Path
) -> PageConfig:
    """Create a new (initially empty) overflow page within the same section.

    Picks a page_number after the last page in `pages` (renumbering happens
    later by the caller).
    """
    last_num = max(p.page_number for p in pages)
    new_folder = workspace / f"_rebal_overflow_{last_num + 1}"
    counter = 0
    while new_folder.exists():
        counter += 1
        new_folder = workspace / f"_rebal_overflow_{last_num + 1}_{counter}"
    new_folder.mkdir(parents=True, exist_ok=False)
    new_page = PageConfig(
        folder=new_folder,
        page_number=last_num + 1,
        photo_count=0,
        layout_seed=ref.layout_seed + 13,
        section_titles=list(ref.section_titles),
        layout_mode=ref.layout_mode,
        section_id=ref.section_id,
        sub_group_ids=list(ref.sub_group_ids),
    )
    logger.info(
        f"Created overflow page after completed neighbor in section "
        f"'{ref.section_titles[0] if ref.section_titles else 'unknown'}'"
    )
    return new_page


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

    temps: list[tuple[PageConfig, Path, Path]] = []
    for page, target in renames:
        tmp = workspace / f"_tmp_rebal_{page.page_number:04d}"
        if page.folder.exists():
            shutil.move(str(page.folder), str(tmp))
        temps.append((page, tmp, target))

    for page, tmp, target in temps:
        if tmp.exists():
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(tmp), str(target))
        page.folder = target


def _move_image(src: Path, dst_folder: Path) -> None:
    """Move an image file into *dst_folder*, renaming to avoid collisions."""
    dst_folder.mkdir(parents=True, exist_ok=True)
    dst = dst_folder / src.name
    counter = 1
    while dst.exists():
        dst = dst_folder / f"{src.stem}_{counter}{src.suffix}"
        counter += 1
    shutil.move(str(src), str(dst))
