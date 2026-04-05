"""Photo sorting: chronological by EXIF date, random fallback for undated."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ingestion.scanner import PhotoInfo

RANDOM_SEED = 42


def sort_photos(
    photos: list[PhotoInfo],
    seed: int = RANDOM_SEED,
) -> list[PhotoInfo]:
    """Sort photos by EXIF date; undated photos are shuffled at the end.

    Within the same source_group, chronological order is preserved.
    Undated photos are shuffled deterministically using *seed*.
    """
    dated = [p for p in photos if p.has_date]
    undated = [p for p in photos if not p.has_date]

    dated.sort(key=lambda p: (p.date_taken, p.source_group, p.path.name))  # type: ignore[arg-type]

    rng = random.Random(seed)
    rng.shuffle(undated)

    return dated + undated
