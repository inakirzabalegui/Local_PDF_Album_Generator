"""Workspace creation: folder structure, image downsampling, and page distribution."""

from __future__ import annotations

import logging
import random
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from src.ingestion.downsampler import downsample_image
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
    
    if cover_photo:
        cover_dir = workspace / COVER_FOLDER
        cover_dir.mkdir()
        dst = cover_dir / f"cover{cover_photo.path.suffix.lower()}"
        downsample_image(cover_photo.path, dst)
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
    # Use special backcover folder if available, otherwise use last photo
    if backcover_candidates:
        backcover_photo = random.choice(backcover_candidates)
        logger.info(f"Usando foto de carpeta 'contraportada': {backcover_photo.path.name}")
        content_photos = photos[1:] if photos else []
    elif len(photos) > 1:
        backcover_photo = photos[-1]
        logger.info(f"Usando última foto para contraportada: {backcover_photo.path.name}")
        content_photos = photos[1:-1]
    else:
        backcover_photo = None
        content_photos = photos[1:] if photos else []

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
        chunks = _chunk_photos_no_mix(group_photos, target_per_page, cfg.photos_per_page_min)
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
        page_configs.append(
            PageConfig(
                folder=back_dir,
                page_number=page_number,
                photo_count=1,
                is_backcover=True,
            )
        )

    return cfg, page_configs


def _chunk_photos_no_mix(
    photos: list[PhotoInfo],
    target: int,
    minimum: int,
) -> list[list[PhotoInfo]]:
    """Split photos into page-sized chunks WITHOUT mixing with other groups.

    If last chunk < minimum, it stays as is (photos will render larger).
    """
    if not photos:
        return []

    chunks: list[list[PhotoInfo]] = []
    for i in range(0, len(photos), target):
        chunks.append(photos[i : i + target])

    return chunks


def _calculate_date_range(dates: list[str]) -> str:
    """Calculate date range string from list of dates in DD/MM/YYYY format."""
    if not dates:
        return ""
    if len(dates) == 1:
        return dates[0]
    
    sorted_dates = sorted(dates, key=lambda d: d.split("/")[::-1])
    return f"{sorted_dates[0]} - {sorted_dates[-1]}"
