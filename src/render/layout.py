"""Photo layout algorithms with justified row-packing collage style.

Places N photos (1–10) on an A4 canvas using justified rows for optimal space usage.
Exhaustive partition enumeration ensures the best possible fill for any photo count
and orientation mix.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4

logger = logging.getLogger("album")

PAGE_W, PAGE_H = A4
BASE_MARGIN = 29  # 10mm minimum margin required by Peecho printing specs
TITLE_SPACE = 40
SUBTITLE_SPACE = 38
BORDER_WIDTH = 4
BASE_GAP = 6  # Gap between photos within rows and between rows

LAYOUT_CONFIGS = {
    "mesa_de_luz": {
        "rotation_range": 3.0,
        "jitter_factor": 0.03,
        "fill_factor": 0.93,
    },
    "grid_compacto": {
        "rotation_range": 0.0,
        "jitter_factor": 0.0,
        "fill_factor": 0.97,
    },
    "hibrido": {
        "rotation_range": 1.5,
        "jitter_factor": 0.01,
        "fill_factor": 0.95,
    },
}


@dataclass
class PlacedPhoto:
    """A photo positioned on the page canvas."""

    path: Path
    x: float
    y: float
    w: float
    h: float
    rotation: float
    z_index: int
    source_group: str = ""


def compute_layout(
    image_paths: list[Path],
    seed: int,
    *,
    layout_mode: str = "mesa_de_luz",
    has_title: bool = False,
    has_subtitle: bool = False,
    weights: list[float] | None = None,
    page_w: float = PAGE_W,
    page_h: float = PAGE_H,
) -> list[PlacedPhoto]:
    """Compute positions for all images on a single page using justified row-packing.

    Args:
        image_paths: List of image file paths
        seed: Random seed for reproducibility
        layout_mode: One of 'mesa_de_luz', 'grid_compacto', 'hibrido'
        has_title: Whether page has main section title
        has_subtitle: Whether page has a secondary sub-section title
        weights: Optional list of weight multipliers (one per photo, default 1.0)
        page_w, page_h: Page dimensions in points
    """
    n = len(image_paths)
    if n == 0:
        return []

    if weights is None:
        weights = [1.0] * n

    config = LAYOUT_CONFIGS.get(layout_mode, LAYOUT_CONFIGS["mesa_de_luz"])
    rng = random.Random(seed)

    margin_top = BASE_MARGIN + (TITLE_SPACE if has_title else 0) + (SUBTITLE_SPACE if has_subtitle else 0)
    margin_side = BASE_MARGIN
    margin_bottom = BASE_MARGIN

    usable_w = page_w - 2 * margin_side
    usable_h = page_h - margin_top - margin_bottom

    # Read actual aspect ratios
    aspect_ratios = [_get_aspect_ratio(p) for p in image_paths]

    # Pack into justified rows (uses effective ARs for weighted photos)
    rows = _justified_rows(aspect_ratios, usable_w, usable_h, BASE_GAP, config["fill_factor"], weights)

    # Calculate total height and center vertically if needed
    total_h = sum(h for _, h in rows) + BASE_GAP * (len(rows) - 1)
    y_offset = max(0, (usable_h - total_h) / 2)
    if y_offset > 0:
        logger.debug(f"    Centering vertically: y_offset={y_offset:.1f}pt")

    # Compute final positions
    placed: list[PlacedPhoto] = []
    current_y = margin_top + y_offset
    photo_idx = 0

    for row_eff_ars, row_h in rows:
        row_photos = image_paths[photo_idx : photo_idx + len(row_eff_ars)]
        row_real_ars = aspect_ratios[photo_idx : photo_idx + len(row_eff_ars)]

        # Calculate actual row width using REAL aspect ratios
        actual_row_w = sum(ar * row_h for ar in row_real_ars) + BASE_GAP * (len(row_real_ars) - 1)

        # Center horizontally
        x_offset = max(0, (usable_w - actual_row_w) / 2)
        current_x = margin_side + x_offset

        for i, (photo_path, real_ar) in enumerate(zip(row_photos, row_real_ars)):
            photo_w = real_ar * row_h
            photo_h = row_h

            # Apply rotation
            rotation = rng.uniform(-config["rotation_range"], config["rotation_range"])

            # Reduce photo size for rotated photos to prevent bounding box bleed
            # Rotated bounding box is larger: w' = w*cos(θ) + h*sin(θ)
            if abs(rotation) > 0.1:
                rad = abs(rotation) * math.pi / 180
                # Reduce by the expansion factor
                reduction = 1.0 / (math.cos(rad) + (photo_h / photo_w) * math.sin(rad))
                reduction = min(reduction, 0.95)  # Max 5% reduction
                photo_w *= reduction
                photo_h *= reduction

            # Apply jitter (reduced to prevent overflow)
            max_jitter = BASE_GAP * config["jitter_factor"] * 0.5  # Reduce jitter by half
            jitter_x = rng.uniform(-max_jitter, max_jitter)
            jitter_y = rng.uniform(-max_jitter, max_jitter)

            x = current_x + jitter_x
            y = current_y + jitter_y

            # Aggressive clamping to page bounds with extra margin
            safety_margin = 2  # Extra 2pt safety margin
            x = max(margin_side + safety_margin, min(x, PAGE_W - margin_side - photo_w - safety_margin))
            y = max(margin_top + safety_margin, min(y, PAGE_H - margin_bottom - photo_h - safety_margin))

            # Compute z-index
            z = _interleaved_z(photo_idx, n, rng)

            placed.append(
                PlacedPhoto(
                    path=photo_path,
                    x=x,
                    y=y,
                    w=photo_w,
                    h=photo_h,
                    rotation=rotation,
                    z_index=z,
                )
            )

            current_x += photo_w + BASE_GAP
            photo_idx += 1

        current_y += row_h + BASE_GAP

    placed.sort(key=lambda p: p.z_index)
    return placed


def score_photo_set(aspect_ratios: list[float], usable_w: float, usable_h: float, gap: float) -> float:
    """Score how well a set of photos with given aspect ratios fills a page.

    Tries all possible partitions into 1-4 rows and returns the best fill score (0.0-1.0).
    """
    n = len(aspect_ratios)
    if n == 0:
        return 0.0

    max_rows = min(n, 4)
    best_score = -1.0

    for num_rows in range(1, max_rows + 1):
        for partition_indices in _all_partitions(n, num_rows):
            row_heights = []
            for start, end in partition_indices:
                row_ars = aspect_ratios[start:end]
                row_h = (usable_w - gap * (len(row_ars) - 1)) / sum(row_ars)
                row_heights.append(row_h)

            total_h = sum(row_heights) + gap * (num_rows - 1)
            score = total_h / usable_h if total_h <= usable_h else usable_h / total_h

            if score > best_score:
                best_score = score

    return best_score


def _justified_rows(
    aspect_ratios: list[float],
    usable_w: float,
    usable_h: float,
    gap: float,
    fill_factor: float,
    weights: list[float] | None = None,
) -> list[tuple[list[float], float]]:
    """Pack photos into justified rows using exhaustive partition enumeration.

    Tries every possible way to split photos into 1–4 rows and picks the
    partition that maximises vertical fill. The fill_factor is applied after
    selection so each layout mode retains its breathing-room character.

    Returns list of (row_aspect_ratios, row_height) tuples.

    weights: Optional list of weight multipliers (one per photo). Weighted
             photos claim more horizontal space by inflating their effective AR.
    """
    n = len(aspect_ratios)
    if n == 0:
        return []

    if weights is None:
        weights = [1.0] * n

    # --- Single photo: constrain both axes ---
    if n == 1:
        ar = aspect_ratios[0]
        # Limit height so that width never exceeds usable_w
        max_h_from_width = usable_w / ar
        row_h = min(usable_h, max_h_from_width) * fill_factor
        return [(aspect_ratios, row_h)]

    # Use effective ARs for layout calculations (weighted photos appear "wider")
    effective_ars = [ar * w for ar, w in zip(aspect_ratios, weights)]

    best_layout: list[tuple[list[float], float]] | None = None
    best_score = -1.0

    max_rows = min(n, 4)

    for num_rows in range(1, max_rows + 1):
        for partition_indices in _all_partitions(n, num_rows):
            row_data: list[tuple[list[float], float]] = []

            for start, end in partition_indices:
                row_eff_ars = effective_ars[start:end]
                row_h = (usable_w - gap * (len(row_eff_ars) - 1)) / sum(row_eff_ars)
                row_data.append((row_eff_ars, row_h))

            total_h = sum(h for _, h in row_data) + gap * (num_rows - 1)

            # Symmetric scoring: 1.0 = perfect fit, <1.0 = under or over fill
            score = total_h / usable_h if total_h <= usable_h else usable_h / total_h

            logger.debug(
                f"    {num_rows} rows partition {partition_indices}: "
                f"total_h={total_h:.1f}pt score={score:.3f}"
            )

            if score > best_score:
                best_score = score
                best_layout = row_data

    logger.debug(f"    Selected layout score={best_score:.3f}")

    if not best_layout:
        return []

    # Apply fill_factor: scale down if over usable_h, or if under apply breathing room
    num_rows = len(best_layout)
    total_h = sum(h for _, h in best_layout) + gap * (num_rows - 1)
    target_h = usable_h * fill_factor

    if total_h > target_h:
        scale = target_h / total_h
        logger.debug(f"    Scaling to fit fill_factor: scale={scale:.3f}")
        best_layout = [(ars, h * scale) for ars, h in best_layout]
    elif total_h > usable_h:
        # Overflow without fill_factor margin: hard-clamp to usable_h
        scale = usable_h / total_h
        logger.debug(f"    Hard-clamping overflow: scale={scale:.3f}")
        best_layout = [(ars, h * scale) for ars, h in best_layout]

    for i, (ars, h) in enumerate(best_layout, 1):
        actual_w = sum(ar * h for ar in ars) + gap * (len(ars) - 1)
        logger.debug(f"    Row {i}: {len(ars)} photos, h={h:.1f}pt, row_w={actual_w:.1f}pt")

    return best_layout


def _all_partitions(n: int, num_groups: int) -> list[list[tuple[int, int]]]:
    """Return all ways to split n ordered items into num_groups non-empty groups.

    Each partition is a list of (start, end) index pairs (end is exclusive).
    Uses combinatorial split-point enumeration: C(n-1, num_groups-1) partitions.

    For n=10, num_groups=4 → C(9,3)=84 partitions. Total across 1–4 groups: ~130.
    """
    if num_groups == 1:
        return [[(0, n)]]
    if num_groups >= n:
        # One item per group
        return [[(i, i + 1) for i in range(n)]]

    result = []
    for splits in combinations(range(1, n), num_groups - 1):
        boundaries = [0] + list(splits) + [n]
        partition = [(boundaries[i], boundaries[i + 1]) for i in range(num_groups)]
        result.append(partition)
    return result


def _get_aspect_ratio(path: Path) -> float:
    """Read image aspect ratio (width/height)."""
    try:
        with Image.open(path) as img:
            w, h = img.size
            if h == 0:
                return 1.33
            return w / h
    except Exception:
        return 1.33  # Default landscape ratio


def _interleaved_z(index: int, total: int, rng: random.Random) -> int:
    """Generate a z-index that creates a natural stacking order."""
    base = index * 2
    return base + rng.randint(0, 1)
