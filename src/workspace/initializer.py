"""Workspace creation: folder structure, image downsampling, and page distribution."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from src.ingestion.downsampler import downsample_image
from src.workspace.config import GlobalConfig, PageConfig

if TYPE_CHECKING:
    from src.ingestion.scanner import PhotoInfo

COVER_FOLDER = "portada"
BACKCOVER_FOLDER = "contraportada"


def create_workspace(
    photos: list[PhotoInfo],
    workspace: Path,
    cfg: GlobalConfig | None = None,
) -> tuple[GlobalConfig, list[PageConfig]]:
    """Build the full workspace directory from a sorted photo list.

    Returns the global config and the list of page configs.
    """
    if cfg is None:
        cfg = GlobalConfig(project_title=workspace.stem.replace("_album", ""))

    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    page_configs: list[PageConfig] = []
    page_number = 0

    # ── Cover ────────────────────────────────────────────────────────────
    if photos:
        cover_photo = photos[0]
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

    # ── Back cover ───────────────────────────────────────────────────────
    backcover_photo = photos[-1] if len(photos) > 1 else None
    content_photos = photos[1:-1] if backcover_photo else photos[1:]

    # ── Content pages ────────────────────────────────────────────────────
    target_per_page = (cfg.photos_per_page_min + cfg.photos_per_page_max) // 2
    chunks = _chunk_photos(content_photos, target_per_page, cfg.photos_per_page_min)

    for idx, chunk in enumerate(chunks):
        folder_name = f"pagina_{page_number:02d}"
        page_dir = workspace / folder_name
        page_dir.mkdir()

        for seq, photo in enumerate(chunk, start=1):
            ext = photo.path.suffix.lower()
            if ext not in (".jpg", ".jpeg"):
                ext = ".jpg"
            dst = page_dir / f"img_{seq:03d}{ext}"
            downsample_image(photo.path, dst)

        page_configs.append(
            PageConfig(
                folder=page_dir,
                page_number=page_number,
                photo_count=len(chunk),
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


def _chunk_photos(
    photos: list[PhotoInfo],
    target: int,
    minimum: int,
) -> list[list[PhotoInfo]]:
    """Split photos into page-sized chunks.

    Each chunk has *target* photos, except possibly the last which gets
    at least *minimum* by pulling from the previous chunk.
    """
    if not photos:
        return []

    chunks: list[list[PhotoInfo]] = []
    for i in range(0, len(photos), target):
        chunks.append(photos[i : i + target])

    if len(chunks) > 1 and len(chunks[-1]) < minimum:
        last = chunks.pop()
        chunks[-1].extend(last)

    return chunks
