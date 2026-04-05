"""Photo sorting: chronological by EXIF date, folder-based fallback for undated."""

from __future__ import annotations

import random
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ingestion.scanner import PhotoInfo

RANDOM_SEED = 42


def sort_photos(
    photos: list[PhotoInfo],
    seed: int = RANDOM_SEED,
) -> list[PhotoInfo]:
    """Sort photos by EXIF date, assigning folder-based dates to undated photos.

    Undated photos receive a synthetic date so they stay grouped with their
    source folder instead of being shuffled to the end:
      1. Folder name YYYYMMDD prefix (if present).
      2. Median EXIF date of sibling photos in the same source_group.
      3. Deterministic random date as last resort.
    """
    _assign_fallback_dates(photos, seed)

    photos.sort(key=lambda p: (p.date_taken, p.source_group, p.path.name))  # type: ignore[arg-type]
    return photos


def _assign_fallback_dates(photos: list[PhotoInfo], seed: int) -> None:
    """Fill in date_taken for photos that lack EXIF dates."""
    # Collect known dates per source_group
    group_dates: dict[str, list[datetime]] = {}
    for p in photos:
        if p.has_date:
            group_dates.setdefault(p.source_group, []).append(p.date_taken)  # type: ignore[arg-type]

    rng = random.Random(seed)

    for p in photos:
        if p.has_date:
            continue

        # Strategy 1: folder name YYYYMMDD prefix
        folder_date = _date_from_folder_name(p.source_group)
        if folder_date:
            offset = rng.randint(0, 86399)
            p.date_taken = folder_date + timedelta(seconds=offset)
            continue

        # Strategy 2: median of sibling EXIF dates
        siblings = group_dates.get(p.source_group)
        if siblings:
            siblings_sorted = sorted(siblings)
            median = siblings_sorted[len(siblings_sorted) // 2]
            offset = rng.randint(0, 86399)
            p.date_taken = median + timedelta(seconds=offset)
            continue

        # Strategy 3: deterministic random date (keeps photos grouped by source_group hash)
        base = datetime(2020, 1, 1) + timedelta(days=hash(p.source_group) % 3650)
        offset = rng.randint(0, 86399)
        p.date_taken = base + timedelta(seconds=offset)


def _date_from_folder_name(name: str) -> datetime | None:
    """Extract a datetime from a YYYYMMDD folder name prefix."""
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", name)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None
