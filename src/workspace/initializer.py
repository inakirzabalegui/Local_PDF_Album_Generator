"""Workspace creation: folder structure, image downsampling, and page distribution."""

from __future__ import annotations

import logging
import math
import random
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from src.ingestion.downsampler import downsample_image
from src.render.layout import score_photo_set, PAGE_W, PAGE_H, BASE_MARGIN, TITLE_SPACE, BASE_GAP
from src.utils.naming import (
    build_section_title,
    extract_date_from_folder,
    folder_name_to_slug,
    prettify_folder_name,
)
from src.workspace.config import GlobalConfig, PageConfig

if TYPE_CHECKING:
    from src.ingestion.scanner import PhotoInfo

logger = logging.getLogger("album")

COVER_FOLDER = "portada"
BACKCOVER_FOLDER = "contraportada"


def create_workspace(
    photos: list[PhotoInfo],
    workspace: Path,
    cfg: GlobalConfig | None = None,
    source_dir_name: str | None = None,
    cover_candidates: list[PhotoInfo] | None = None,
    backcover_candidates: list[PhotoInfo] | None = None,
    progress_callback=None,
) -> tuple[GlobalConfig, list[PageConfig]]:
    """Build the full workspace directory from a sorted photo list.

    If cover_candidates or backcover_candidates are provided, a random photo
    from those lists will be used. Otherwise, falls back to first/last photo
    from the main photo list.

    Returns the global config and the list of page configs.
    """
    if cfg is None:
        if source_dir_name:
            title = prettify_folder_name(source_dir_name)
        else:
            title = workspace.stem.replace("_album", "")
        cfg = GlobalConfig(project_title=title)

    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    page_configs: list[PageConfig] = []
    page_number = 0

    # ── Cover ────────────────────────────────────────────────────────────
    # Use special cover folder if available, otherwise use first photo
    if cover_candidates:
        cover_photo = random.choice(cover_candidates)
        logger.info(f"Usando foto de carpeta 'portada': {cover_photo.path.name}")
    elif photos:
        cover_photo = photos[0]
        logger.info(f"Usando primera foto para portada: {cover_photo.path.name}")
    else:
        cover_photo = None

    # ── Back cover selection ─────────────────────────────────────────────
    # Determine early so we can calculate total for progress reporting
    if backcover_candidates:
        _backcover_photo_pre = random.choice(backcover_candidates)
        _content_photos_pre = photos[1:] if photos else []
    elif len(photos) > 1:
        _backcover_photo_pre = photos[-1]
        _content_photos_pre = photos[1:-1]
    else:
        _backcover_photo_pre = None
        _content_photos_pre = photos[1:] if photos else []

    _total_downloads = (
        (1 if cover_photo else 0)
        + len(_content_photos_pre)
        + (1 if _backcover_photo_pre else 0)
    )
    _downloaded = [0]

    def _progress(photo_path):
        _downloaded[0] += 1
        if progress_callback:
            progress_callback({
                "step": "processing",
                "current": _downloaded[0],
                "total": _total_downloads,
                "name": photo_path.name,
            })

    if cover_photo:
        cover_dir = workspace / COVER_FOLDER
        cover_dir.mkdir()
        dst = cover_dir / f"cover{cover_photo.path.suffix.lower()}"
        downsample_image(cover_photo.path, dst)
        _progress(cover_photo.path)
        page_configs.append(
            PageConfig(
                folder=cover_dir,
                page_number=page_number,
                photo_count=1,
                is_cover=True,
            )
        )
        page_number += 1

    # ── Back cover selection ─────────────────────────────────────────────
    backcover_photo = _backcover_photo_pre
    content_photos = _content_photos_pre
    if backcover_photo:
        logger.info(
            f"{'Usando foto de carpeta contraportada' if backcover_candidates else 'Usando última foto para contraportada'}: "
            f"{backcover_photo.path.name}"
        )

    # ── Content pages: group by source_group WITHOUT mixing ─────────────
    all_dates = []
    groups_dict: dict[str, list[PhotoInfo]] = {}
    for photo in content_photos:
        if photo.source_group not in groups_dict:
            groups_dict[photo.source_group] = []
            date = extract_date_from_folder(photo.source_group)
            if date:
                all_dates.append(date)
        groups_dict[photo.source_group].append(photo)

    logger.debug(f"Grouped content photos into {len(groups_dict)} source groups")
    for group_name, group_photos in groups_dict.items():
        logger.debug(f"  {group_name}: {len(group_photos)} photos")

    cfg.date_range = _calculate_date_range(all_dates)
    logger.debug(f"Calculated album date range: {cfg.date_range}")

    target_per_page = (cfg.photos_per_page_min + cfg.photos_per_page_max) // 2
    layout_modes = ["mesa_de_luz", "grid_compacto", "hibrido"]

    import random as _rnd

    for source_group, group_photos in groups_dict.items():
        chunks = _chunk_photos_by_orientation(group_photos, target_per_page, cfg.photos_per_page_min, cfg.photos_per_page_max)
        logger.debug(f"Chunking {source_group}: {len(group_photos)} photos into {len(chunks)} pages")
        
        section_title = build_section_title(source_group)
        title_slug = folder_name_to_slug(prettify_folder_name(source_group))

        # Track which sub_groups have already had their banner shown
        seen_sub_groups: set[str] = set()

        for chunk_idx, chunk in enumerate(chunks, 1):
            folder_name = f"pagina_{page_number:02d}_{title_slug}"
            page_dir = workspace / folder_name
            page_dir.mkdir()

            actual_count = 0
            for seq, photo in enumerate(chunk, start=1):
                ext = photo.path.suffix.lower()
                if ext not in (".jpg", ".jpeg"):
                    ext = ".jpg"
                dst = page_dir / f"img_{seq:03d}{ext}"
                if downsample_image(photo.path, dst) is not None:
                    actual_count += 1
                _progress(photo.path)

            # Determine if any new sub_groups start on this page
            new_subs = []
            for photo in chunk:
                if photo.sub_group and photo.sub_group not in seen_sub_groups:
                    seen_sub_groups.add(photo.sub_group)
                    new_subs.append(photo.sub_group)

            titles = [section_title]
            if new_subs:
                sub_label = " / ".join(prettify_folder_name(s) for s in new_subs)
                titles.append(sub_label)
                logger.debug(f"  Sub-banner on page {page_number}: {sub_label}")

            selected_mode = _rnd.choice(layout_modes)
            
            logger.debug(
                f"  Chunk {chunk_idx}/{len(chunks)}: page_{page_number:02d}, "
                f"{len(chunk)} photos, mode={selected_mode}"
            )

            page_configs.append(
                PageConfig(
                    folder=page_dir,
                    page_number=page_number,
                    photo_count=actual_count,
                    section_titles=titles,
                    layout_mode=selected_mode,
                )
            )
            page_number += 1

    # ── Back cover (placed last) ─────────────────────────────────────────
    if backcover_photo:
        back_dir = workspace / BACKCOVER_FOLDER
        back_dir.mkdir()
        dst = back_dir / f"backcover{backcover_photo.path.suffix.lower()}"
        downsample_image(backcover_photo.path, dst)
        _progress(backcover_photo.path)
        page_configs.append(
            PageConfig(
                folder=back_dir,
                page_number=page_number,
                photo_count=1,
                is_backcover=True,
            )
        )

    return cfg, page_configs


def _chunk_photos_by_orientation(
    photos: list[PhotoInfo],
    target: int,
    minimum: int,
    maximum: int,
) -> list[list[PhotoInfo]]:
    if not photos:
        return []

    n = len(photos)
    if n <= target:
        return [photos]

    usable_w = PAGE_W - 2 * BASE_MARGIN
    usable_h = PAGE_H - BASE_MARGIN - BASE_MARGIN - TITLE_SPACE

    ars = [p.width / p.height if p.height else 1.33 for p in photos]

    sorted_indices = sorted(range(n), key=lambda i: ars[i])

    base = math.ceil(n / target)
    candidates = [base - 1, base, base + 1]

    best_num_pages = base
    best_total_score = -1.0

    for num_pages in candidates:
        if num_pages < 1:
            continue
        photos_per = n / num_pages
        if photos_per < minimum or photos_per > maximum:
            continue

        group_size = n / num_pages
        total_score = 0.0
        for g in range(num_pages):
            start = round(g * group_size)
            end = round((g + 1) * group_size)
            group_sorted_indices = sorted_indices[start:end]
            group_ars = [ars[i] for i in group_sorted_indices]
            total_score += score_photo_set(group_ars, usable_w, usable_h, BASE_GAP)

        if total_score > best_total_score:
            best_total_score = total_score
            best_num_pages = num_pages

    group_size = n / best_num_pages
    chunks: list[list[PhotoInfo]] = []
    for g in range(best_num_pages):
        start = round(g * group_size)
        end = round((g + 1) * group_size)
        group_sorted_indices = sorted_indices[start:end]
        group_original_order = sorted(group_sorted_indices)
        chunks.append([photos[i] for i in group_original_order])

    if len(chunks) > 1 and len(chunks[-1]) == 1:
        last = chunks.pop()
        chunks[-1].extend(last)

    return chunks


def _calculate_date_range(dates: list[str]) -> str:
    """Calculate date range string from list of dates in DD/MM/YYYY format."""
    if not dates:
        return ""
    if len(dates) == 1:
        return dates[0]
    
    sorted_dates = sorted(dates, key=lambda d: d.split("/")[::-1])
    return f"{sorted_dates[0]} - {sorted_dates[-1]}"
