"""Cascade rebalancing of page folders when photo counts are out of range."""

from __future__ import annotations

import shutil
from pathlib import Path

from src.workspace.config import (
    GlobalConfig,
    PageConfig,
    VALID_IMAGE_EXTENSIONS,
    write_page_configs,
)


def rebalance(
    pages: list[PageConfig],
    cfg: GlobalConfig,
    workspace: Path,
) -> list[PageConfig]:
    """Rebalance photos across content pages so every page has min..max photos.

    Cover and backcover pages are excluded from rebalancing.
    Rebalancing only occurs within pages of the same group (same section_titles).
    Returns the updated (and potentially rewritten) page list.
    """
    content = [p for p in pages if not p.is_cover and not p.is_backcover]
    special = [p for p in pages if p.is_cover or p.is_backcover]

    if not content:
        return pages

    groups = _group_by_section(content)
    changed = False

    for group_pages in groups.values():
        if len(group_pages) <= 1:
            continue
        
        changed_fwd = _cascade_forward(group_pages, cfg)
        changed_bwd = _cascade_backward(group_pages, cfg)
        changed = changed or changed_fwd or changed_bwd

    if changed:
        for pc in content:
            pc.photo_count = len(pc.image_files())
        write_page_configs(content)
        print("[rebalance] Páginas rebalanceadas y YAMLs actualizados.")
    else:
        print("[rebalance] No se requieren cambios.")

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


def _cascade_forward(pages: list[PageConfig], cfg: GlobalConfig) -> bool:
    """Push excess photos from page[i] to page[i+1]."""
    changed = False
    for i in range(len(pages) - 1):
        images = pages[i].image_files()
        if len(images) > cfg.photos_per_page_max:
            excess = images[cfg.photos_per_page_max :]
            for img in excess:
                _move_image(img, pages[i + 1].folder)
            changed = True
    return changed


def _cascade_backward(pages: list[PageConfig], cfg: GlobalConfig) -> bool:
    """Pull photos from page[i+1] into page[i] if page[i] is below min."""
    changed = False
    for i in range(len(pages) - 1):
        images = pages[i].image_files()
        deficit = cfg.photos_per_page_min - len(images)
        if deficit > 0:
            next_images = pages[i + 1].image_files()
            to_pull = next_images[:deficit]
            for img in to_pull:
                _move_image(img, pages[i].folder)
            changed = True
    return changed


def _move_image(src: Path, dst_folder: Path) -> None:
    """Move an image file into *dst_folder*, renaming to avoid collisions."""
    dst_folder.mkdir(parents=True, exist_ok=True)
    dst = dst_folder / src.name
    counter = 1
    while dst.exists():
        dst = dst_folder / f"{src.stem}_{counter}{src.suffix}"
        counter += 1
    shutil.move(str(src), str(dst))
