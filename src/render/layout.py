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
TITLE_SPACE = 30  # Reduced from 40 for more vertical space
SUBTITLE_SPACE = 62  # Must exceed secondary bar bottom (≈114pt from top) so photos never overlap
BORDER_WIDTH = 4
BASE_GAP = 4  # Gap between photos within rows and between rows (reduced from 6)

LAYOUT_CONFIGS = {
    "mesa_de_luz": {
        "rotation_range": 3.0,
        "jitter_factor": 0.03,
        "fill_factor": 0.96,  # Increased from 0.93 to pack photos more densely
    },
    "grid_compacto": {
        "rotation_range": 0.0,
        "jitter_factor": 0.0,
        "fill_factor": 0.97,
    },
    "hibrido": {
        "rotation_range": 1.5,
        "jitter_factor": 0.01,
        "fill_factor": 0.97,  # Increased from 0.95 to pack photos more densely
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


def _try_mosaic_layout(
    image_paths: list[Path],
    aspect_ratios: list[float],
    usable_w: float,
    usable_h: float,
    gap: float,
    fill_factor: float,
    weights: list[float],
) -> list[tuple[list[float], float]] | None:
    """Try mosaic/guillotine layout when weighted photos are present.
    
    Picks the heaviest photo as hero, allocates proportional area, 
    then recursively packs remaining photos.
    
    Returns layout data if score > 0.75, else None (fall back to row/column).
    """
    n = len(image_paths)
    if n < 2:
        return None
    
    # Find hero (highest weight)
    max_weight_idx = max(range(n), key=lambda i: weights[i])
    hero_weight = weights[max_weight_idx]
    
    # If no real hero (all weights ~1.0), skip mosaic
    if hero_weight <= 1.1:
        return None
    
    hero_ar = aspect_ratios[max_weight_idx]
    
    # Allocate hero area proportional to its weight share
    total_weight = sum(weights)
    hero_area_fraction = hero_weight / total_weight
    hero_area_fraction = max(0.20, min(0.40, hero_area_fraction))
    
    # Hero takes a rectangular region (left side, tall)
    hero_h = usable_h
    hero_w = min(usable_w * 0.5, (hero_h * hero_ar) * (hero_area_fraction / (hero_area_fraction / hero_ar)))
    hero_w = max(usable_w * 0.25, hero_w)
    
    # Remaining space to the right
    remaining_w = usable_w - hero_w - gap
    remaining_h = usable_h
    
    if remaining_w < 100:  # Too little space left, bail
        return None
    
    # Pack remaining photos into remaining_w x remaining_h
    remaining_indices = [i for i in range(n) if i != max_weight_idx]
    remaining_ars = [aspect_ratios[i] for i in remaining_indices]
    remaining_weights = [weights[i] for i in remaining_indices]
    
    effective_ars = [ar * w for ar, w in zip(remaining_ars, remaining_weights)]
    
    # Try row-major packing in the remaining space
    best_layout = None
    best_score = -1.0
    
    max_rows = min(len(remaining_indices), 4)
    for num_rows in range(1, max_rows + 1):
        for partition_indices in _all_partitions(len(remaining_indices), num_rows):
            row_data = []
            for start, end in partition_indices:
                row_eff_ars = effective_ars[start:end]
                row_h = (remaining_w - gap * (len(row_eff_ars) - 1)) / sum(row_eff_ars)
                row_data.append((row_eff_ars, row_h))
            
            total_h = sum(h for _, h in row_data) + gap * (num_rows - 1)
            
            # Score the remaining space
            v_fill = min(total_h, remaining_h) / remaining_h
            if v_fill < 0.75:
                v_score = v_fill ** 2
            else:
                v_score = 1.0 if total_h <= remaining_h else (remaining_h / total_h) ** 0.5
            
            if total_h > remaining_h:
                overflow_penalty = (remaining_h / total_h) ** 1.5
            else:
                overflow_penalty = 1.0
            
            score = v_score * overflow_penalty
            
            if score > best_score:
                best_score = score
                best_layout = row_data
    
    if best_layout and best_score > 0.60:
        # Return combined layout: hero + remaining rows
        # For simplicity, prepend hero as its own "row" with special width
        return [(aspect_ratios[max_weight_idx:max_weight_idx+1], hero_w)] + best_layout
    
    return None


def _try_column_major_layout(
    aspect_ratios: list[float],
    usable_w: float,
    usable_h: float,
    gap: float,
    fill_factor: float,
    weights: list[float] | None = None,
) -> tuple[list[tuple[list[float], float]], str] | None:
    """Try column-major packing and return (columns, "column_major") if viable.
    
    Each column stacks photos vertically to fill usable_h.
    Returns None if this layout is worse than row-major.
    """
    n = len(aspect_ratios)
    if n <= 2:
        return None  # Not worth trying for 1-2 photos

    if weights is None:
        weights = [1.0] * n

    effective_ars = [ar * w for ar, w in zip(aspect_ratios, weights)]
    
    best_layout = None
    best_score = -1.0
    
    # Try 2-5 columns
    for num_cols in range(2, min(n, 6)):
        for partition_indices in _all_partitions(n, num_cols):
            col_data: list[tuple[list[float], float]] = []
            
            for start, end in partition_indices:
                col_eff_ars = effective_ars[start:end]
                col_real_ars = aspect_ratios[start:end]
                
                # Column must stack photos vertically to fill usable_h
                # col_w = usable_h / (sum of 1/AR for each photo in column + gaps)
                sum_inv_ar = sum(1.0 / ar for ar in col_real_ars)
                col_w = (usable_h - gap * (len(col_real_ars) - 1)) / sum_inv_ar
                
                col_data.append((col_eff_ars, col_w))
            
            total_w = sum(w for _, w in col_data) + gap * (num_cols - 1)
            
            # Score: measure horizontal fill
            h_fill = min(total_w, usable_w) / usable_w
            if h_fill < 0.75:
                h_fill_score = h_fill ** 2
            else:
                h_fill_score = 1.0 if total_w <= usable_w else (usable_w / total_w) ** 0.5
            
            if total_w > usable_w:
                overflow_penalty = (usable_w / total_w) ** 1.5
            else:
                overflow_penalty = 1.0
            
            score = h_fill_score * overflow_penalty
            
            if score > best_score:
                best_score = score
                best_layout = col_data
    
    if best_layout and best_score > 0.70:
        return (best_layout, "column_major")
    return None


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
    """Compute positions for all images on a single page.

    Tries mosaic (if weighted), column-major, then row-major packing.
    For 1–4 photos, offers a 2x2 exception layout if dense packing scores poorly.

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

    # Packer selection with fallback chain
    rows_or_cols = None
    is_column_major = False
    is_mosaic = False
    
    # Try mosaic if weighted photos present
    if any(w > 1.1 for w in weights):
        rows_or_cols = _try_mosaic_layout(
            image_paths, aspect_ratios, usable_w, usable_h, BASE_GAP, config["fill_factor"], weights
        )
        is_mosaic = rows_or_cols is not None
    
    # Try column-major if mosaic didn't work
    if not is_mosaic:
        col_result = _try_column_major_layout(
            aspect_ratios, usable_w, usable_h, BASE_GAP, config["fill_factor"], weights
        )
        if col_result:
            rows_or_cols, layout_type = col_result
            is_column_major = layout_type == "column_major"
    
    # Fall back to row-major
    if rows_or_cols is None:
        rows_or_cols = _justified_rows(aspect_ratios, usable_w, usable_h, BASE_GAP, config["fill_factor"], weights)
    
    # 2x2 exception for small photo counts
    if n <= 4 and not is_mosaic and not is_column_major:
        # Check if best row-major layout is sparse (fill < 75%)
        total_h = sum(h for _, h in rows_or_cols) + BASE_GAP * (len(rows_or_cols) - 1)
        fill_ratio = min(total_h, usable_h) / usable_h
        
        if fill_ratio < 0.75 and n >= 3:
            logger.debug(f"    Using 2x2 grid exception for {n} photos (fill={fill_ratio:.2f})")
            return _compute_grid_layout(
                image_paths, aspect_ratios, n, usable_w, usable_h, 
                margin_side, margin_top, config, rng
            )

    # Calculate total size and center
    if is_column_major or is_mosaic:
        total_w = sum(w for _, w in rows_or_cols) + BASE_GAP * (len(rows_or_cols) - 1)
        x_offset = max(0, (usable_w - total_w) / 2)
        y_offset = 0
    else:
        total_h = sum(h for _, h in rows_or_cols) + BASE_GAP * (len(rows_or_cols) - 1)
        y_offset = max(0, (usable_h - total_h) / 2)
        x_offset = 0

    # Compute final positions
    placed: list[PlacedPhoto] = []
    photo_idx = 0

    if is_column_major or is_mosaic:
        # Column-major or mosaic placement
        current_x = margin_side + x_offset
        for col_eff_ars, col_w in rows_or_cols:
            col_real_ars = aspect_ratios[photo_idx : photo_idx + len(col_eff_ars)]
            col_photos = image_paths[photo_idx : photo_idx + len(col_eff_ars)]
            
            current_y = margin_top
            for photo_path, real_ar in zip(col_photos, col_real_ars):
                photo_w = col_w
                photo_h = col_w / real_ar
                
                rotation = rng.uniform(-config["rotation_range"], config["rotation_range"])
                if abs(rotation) > 0.1:
                    rad = abs(rotation) * math.pi / 180
                    reduction = 1.0 / (math.cos(rad) + (photo_h / photo_w) * math.sin(rad))
                    reduction = min(reduction, 0.95)
                    photo_w *= reduction
                    photo_h *= reduction
                
                max_jitter = BASE_GAP * config["jitter_factor"] * 0.5
                jitter_x = rng.uniform(-max_jitter, max_jitter)
                jitter_y = rng.uniform(-max_jitter, max_jitter)
                
                x = current_x + jitter_x
                y = current_y + jitter_y
                
                safety_margin = 2
                x = max(margin_side + safety_margin, min(x, PAGE_W - margin_side - photo_w - safety_margin))
                y = max(margin_top + safety_margin, min(y, PAGE_H - margin_bottom - photo_h - safety_margin))
                
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
                
                current_y += col_w / real_ar + BASE_GAP
                photo_idx += 1
            
            current_x += col_w + BASE_GAP
    else:
        # Row-major placement
        current_y = margin_top + y_offset
        for row_eff_ars, row_h in rows_or_cols:
            row_photos = image_paths[photo_idx : photo_idx + len(row_eff_ars)]
            row_real_ars = aspect_ratios[photo_idx : photo_idx + len(row_eff_ars)]

            actual_row_w = sum(ar * row_h for ar in row_real_ars) + BASE_GAP * (len(row_real_ars) - 1)
            x_offset_row = max(0, (usable_w - actual_row_w) / 2)
            current_x = margin_side + x_offset_row

            for i, (photo_path, real_ar) in enumerate(zip(row_photos, row_real_ars)):
                photo_w = real_ar * row_h
                photo_h = row_h

                rotation = rng.uniform(-config["rotation_range"], config["rotation_range"])

                if abs(rotation) > 0.1:
                    rad = abs(rotation) * math.pi / 180
                    reduction = 1.0 / (math.cos(rad) + (photo_h / photo_w) * math.sin(rad))
                    reduction = min(reduction, 0.95)
                    photo_w *= reduction
                    photo_h *= reduction

                max_jitter = BASE_GAP * config["jitter_factor"] * 0.5
                jitter_x = rng.uniform(-max_jitter, max_jitter)
                jitter_y = rng.uniform(-max_jitter, max_jitter)

                x = current_x + jitter_x
                y = current_y + jitter_y

                safety_margin = 2
                x = max(margin_side + safety_margin, min(x, PAGE_W - margin_side - photo_w - safety_margin))
                y = max(margin_top + safety_margin, min(y, PAGE_H - margin_bottom - photo_h - safety_margin))

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


def _compute_grid_layout(
    image_paths: list[Path],
    aspect_ratios: list[float],
    n: int,
    usable_w: float,
    usable_h: float,
    margin_side: float,
    margin_top: float,
    config: dict,
    rng: random.Random,
) -> list[PlacedPhoto]:
    """Compute a simple 2x2 grid layout for 3-4 photos (exception case)."""
    grid_cols = 2
    grid_rows = (n + 1) // 2
    
    cell_w = (usable_w - BASE_GAP * (grid_cols - 1)) / grid_cols
    cell_h = (usable_h - BASE_GAP * (grid_rows - 1)) / grid_rows
    
    cell_size = min(cell_w, cell_h)
    
    total_w = grid_cols * cell_size + BASE_GAP * (grid_cols - 1)
    total_h = grid_rows * cell_size + BASE_GAP * (grid_rows - 1)
    
    x_offset = (usable_w - total_w) / 2
    y_offset = (usable_h - total_h) / 2
    
    placed = []
    for i, (photo_path, ar) in enumerate(zip(image_paths, aspect_ratios)):
        row = i // grid_cols
        col = i % grid_cols
        
        cell_x = margin_side + x_offset + col * (cell_size + BASE_GAP)
        cell_y = margin_top + y_offset + row * (cell_size + BASE_GAP)
        
        photo_w = cell_size * 0.9
        photo_h = photo_w / ar
        if photo_h > cell_size * 0.9:
            photo_h = cell_size * 0.9
            photo_w = photo_h * ar
        
        x = cell_x + (cell_size - photo_w) / 2
        y = cell_y + (cell_size - photo_h) / 2
        
        z = _interleaved_z(i, n, rng)
        
        placed.append(
            PlacedPhoto(
                path=photo_path,
                x=x,
                y=y,
                w=photo_w,
                h=photo_h,
                rotation=0.0,
                z_index=z,
            )
        )
    
    return placed


def score_photo_set(aspect_ratios: list[float], usable_w: float, usable_h: float, gap: float) -> float:
    """Score how well a set of photos with given aspect ratios fills a page.

    Tries all possible partitions into 1-5 rows and returns the best fill score (0.0-1.0).
    """
    n = len(aspect_ratios)
    if n == 0:
        return 0.0

    max_rows = min(n, 5)
    best_score = -1.0

    for num_rows in range(1, max_rows + 1):
        for partition_indices in _all_partitions(n, num_rows):
            row_heights = []
            for start, end in partition_indices:
                row_ars = aspect_ratios[start:end]
                row_h = (usable_w - gap * (len(row_ars) - 1)) / sum(row_ars)
                row_heights.append(row_h)

            total_h = sum(row_heights) + gap * (num_rows - 1)
            score = _score_layout_quality(total_h, usable_h, usable_w, row_heights, aspect_ratios, gap)

            if score > best_score:
                best_score = score

    return best_score


def _score_layout_quality(
    total_h: float, usable_h: float, usable_w: float, 
    row_heights: list[float], aspect_ratios: list[float], gap: float
) -> float:
    """Score layout quality based on fill efficiency and size balance.
    
    Returns a score 0.0-1.0 where higher is better.
    Hard penalty for under-fill (< 80% vertical usage).
    """
    # Compute fill ratio
    fill = min(total_h, usable_h) / usable_h
    
    # Hard penalty for under-fill
    if fill < 0.80:
        fill_score = fill ** 2
    else:
        fill_score = 1.0 if total_h <= usable_h else (usable_h / total_h) ** 0.5
    
    # Compute size balance (penalize extreme variance)
    if len(aspect_ratios) > 1:
        # Estimate photo sizes based on their ARs and the computed row heights
        photo_sizes = []
        photo_idx = 0
        for row_h in row_heights:
            for ar in aspect_ratios[photo_idx : photo_idx + len(aspect_ratios)]:
                if photo_idx < len(aspect_ratios):
                    photo_w = ar * row_h
                    photo_h = row_h
                    photo_sizes.append(photo_w * photo_h)
                    photo_idx += 1
                    if photo_idx >= len(aspect_ratios):
                        break
            if photo_idx >= len(aspect_ratios):
                break
        
        if photo_sizes and len(photo_sizes) > 1:
            min_size = min(photo_sizes)
            max_size = max(photo_sizes)
            size_ratio = min_size / max_size if max_size > 0 else 1.0
            size_balance = 0.3 + 0.7 * size_ratio  # Range [0.3, 1.0]
        else:
            size_balance = 1.0
    else:
        size_balance = 1.0
    
    # Overflow penalty
    if total_h > usable_h:
        overflow_penalty = (usable_h / total_h) ** 1.5
    else:
        overflow_penalty = 1.0
    
    return fill_score * size_balance * overflow_penalty


def _justified_rows(
    aspect_ratios: list[float],
    usable_w: float,
    usable_h: float,
    gap: float,
    fill_factor: float,
    weights: list[float] | None = None,
) -> list[tuple[list[float], float]]:
    """Pack photos into justified rows using exhaustive partition enumeration.

    Tries every possible way to split photos into 1–5 rows and picks the
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

    max_rows = min(n, 5)

    for num_rows in range(1, max_rows + 1):
        for partition_indices in _all_partitions(n, num_rows):
            row_data: list[tuple[list[float], float]] = []

            for start, end in partition_indices:
                row_eff_ars = effective_ars[start:end]
                row_h = (usable_w - gap * (len(row_eff_ars) - 1)) / sum(row_eff_ars)
                row_data.append((row_eff_ars, row_h))

            total_h = sum(h for _, h in row_data) + gap * (num_rows - 1)

            # Use new quality-based scoring
            score = _score_layout_quality(total_h, usable_h, usable_w, 
                                         [h for _, h in row_data], aspect_ratios, gap)

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
