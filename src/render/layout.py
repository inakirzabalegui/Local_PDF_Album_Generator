"""Photo layout algorithms with justified row-packing collage style.

Places N photos (1–10) on a configurable trim area using justified rows for
optimal space usage. Exhaustive partition enumeration ensures the best possible
fill for any photo count and orientation mix.

Page dimensions and margins are passed in by the caller (derived from the
provider's PageSpec + per-parity safe insets).
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from PIL import Image

logger = logging.getLogger("album")

TITLE_SPACE = 30  # Reduced from 40 for more vertical space
SUBTITLE_SPACE = 62  # Must exceed secondary bar bottom (≈114pt from top) so photos never overlap
BORDER_WIDTH = 4
BASE_GAP = 4  # Gap between photos within rows and between rows

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
    "cuadricula_uniforme": {
        # Strict N×M grid. Cells fill the full usable area; photos letterboxed
        # inside cells (AR preserved). Inner-cell whitespace is possible when
        # cell AR differs from photo AR. Ignores per-photo weights.
        "rotation_range": 0.0,
        "jitter_factor": 0.0,
        "fill_factor": 0.98,
        "grid_fit": "contain",
    },
    "cuadricula_compacta": {
        # Same letterbox semantics, but cells are sized to the photo's native AR
        # so there is no whitespace INSIDE the cells. The grid as a whole is
        # smaller than the usable area and centered on the page. Photos end up
        # the same size as `cuadricula_uniforme` but visually packed tight.
        "rotation_range": 0.0,
        "jitter_factor": 0.0,
        "fill_factor": 1.0,
        "grid_fit": "compact",
    },
    "cuadricula_maximizada": {
        # Cells fill the full usable area and photos are scaled to FILL each
        # cell (crop-to-cover): photo content may be clipped at the edges, but
        # photos are visually maximal. Best when you want every pixel of page
        # used. Ignores per-photo weights.
        "rotation_range": 0.0,
        "jitter_factor": 0.0,
        "fill_factor": 1.0,
        "grid_fit": "cover",
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
    # How the renderer should fit the image into the (w, h) rectangle:
    #   "contain" (default): preserve AR, letterbox inside the rectangle
    #   "cover": scale to fill the rectangle, cropping the overflow
    fit_mode: str = "contain"


def _try_mosaic_layout(
    image_paths: list[Path],
    aspect_ratios: list[float],
    usable_w: float,
    usable_h: float,
    gap: float,
    fill_factor: float,
    weights: list[float],
) -> dict | None:
    """Try mosaic layout when a weighted hero photo is present.

    Places the hero in a reserved column on the LEFT of the usable area
    and packs the remaining photos as justified rows inside the right
    sub-rectangle (reuses `_justified_rows`).

    Returns a dict with explicit per-photo rects in the *usable* frame
    so the caller can place each photo using its real index in
    ``image_paths`` (avoids the old positional-slicing bug where the
    hero ended up at the wrong photo when filenames weren't sorted by
    weight).

    Shape::

        {
            "kind": "mosaic",
            "hero":      {"index": int, "rect": (x, y, w, h)},
            "remaining": [{"index": int, "rect": (x, y, w, h)}, ...],
        }

    Returns ``None`` if no weighted photo qualifies as hero, if there is
    no room left for the remaining photos, or if the remaining packing
    would overflow the right sub-rectangle.
    """
    n = len(image_paths)
    if n < 2:
        return None

    max_weight_idx = max(range(n), key=lambda i: weights[i])
    hero_weight = weights[max_weight_idx]
    if hero_weight <= 1.1:
        return None

    hero_ar = aspect_ratios[max_weight_idx]
    total_weight = sum(weights)
    hero_area_fraction = max(0.20, min(0.40, hero_weight / total_weight))

    # Reserved column width for the hero on the LEFT of the usable area.
    hero_w = max(usable_w * 0.30, min(usable_w * 0.55, usable_w * hero_area_fraction))
    if hero_ar < 1.0:
        # Portrait hero — don't reserve more width than the photo can fill at full height.
        hero_w = min(hero_w, usable_h * hero_ar)

    remaining_w = usable_w - hero_w - gap
    remaining_h = usable_h
    if remaining_w < 100:
        return None

    # Hero photo's actual rect inside its reserved column (AR-preserved, centered).
    hero_natural_h = hero_w / hero_ar
    if hero_natural_h <= usable_h:
        hero_photo_w = hero_w
        hero_photo_h = hero_natural_h
    else:
        hero_photo_h = usable_h
        hero_photo_w = usable_h * hero_ar
    hero_x = (hero_w - hero_photo_w) / 2
    hero_y = (usable_h - hero_photo_h) / 2

    remaining_indices = [i for i in range(n) if i != max_weight_idx]
    remaining_ars = [aspect_ratios[i] for i in remaining_indices]
    remaining_weights = [weights[i] for i in remaining_indices]

    row_layout = _justified_rows(
        remaining_ars, remaining_w, remaining_h, gap, fill_factor, remaining_weights
    )
    if not row_layout:
        return None

    total_rows_h = sum(h for _, h in row_layout) + gap * (len(row_layout) - 1)
    if total_rows_h > remaining_h + 0.5:
        # _justified_rows should have scaled to fit, but bail if it didn't.
        return None

    remaining_x_offset = hero_w + gap
    row_y_offset = max(0.0, (remaining_h - total_rows_h) / 2)
    remaining_entries: list[dict] = []
    rem_idx = 0
    current_y = row_y_offset
    for row_eff_ars, row_h in row_layout:
        row_count = len(row_eff_ars)
        row_real_ars = remaining_ars[rem_idx : rem_idx + row_count]
        actual_row_w = sum(ar * row_h for ar in row_real_ars) + gap * (row_count - 1)
        x_offset_row = max(0.0, (remaining_w - actual_row_w) / 2)
        current_x = remaining_x_offset + x_offset_row
        for k, real_ar in enumerate(row_real_ars):
            photo_w = real_ar * row_h
            photo_h = row_h
            remaining_entries.append({
                "index": remaining_indices[rem_idx + k],
                "rect": (current_x, current_y, photo_w, photo_h),
            })
            current_x += photo_w + gap
        rem_idx += row_count
        current_y += row_h + gap

    logger.debug(
        f"    Mosaic: hero idx={max_weight_idx} rect=({hero_x:.1f},{hero_y:.1f},"
        f"{hero_photo_w:.1f},{hero_photo_h:.1f}); "
        f"{len(remaining_entries)} remaining photos in {len(row_layout)} rows"
    )

    return {
        "kind": "mosaic",
        "hero": {
            "index": max_weight_idx,
            "rect": (hero_x, hero_y, hero_photo_w, hero_photo_h),
        },
        "remaining": remaining_entries,
    }


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


def _rotate_and_jitter(
    photo_w: float, photo_h: float, config: dict, rng: random.Random,
) -> tuple[float, float, float, float, float]:
    """Apply rotation shrink + jitter for one photo.

    RNG call order: rotation → jitter_x → jitter_y (3 calls). Critical: callers
    must invoke this once per photo in the same order as the original inline
    code so the deterministic seeded RNG produces byte-identical output.

    Returns (photo_w_adjusted, photo_h_adjusted, rotation, jitter_x, jitter_y).
    """
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
    return photo_w, photo_h, rotation, jitter_x, jitter_y


def _clamp_to_page(
    x: float, y: float, photo_w: float, photo_h: float,
    margin_left: float, effective_margin_top: float,
    page_w: float, page_h: float, margin_right: float, margin_bottom: float,
) -> tuple[float, float]:
    """Clamp (x, y) so the photo stays inside the safe-print area."""
    safety_margin = 2
    x = max(margin_left + safety_margin, min(x, page_w - margin_right - photo_w - safety_margin))
    y = max(effective_margin_top + safety_margin, min(y, page_h - margin_bottom - photo_h - safety_margin))
    return x, y


def compute_layout(
    image_paths: list[Path],
    seed: int,
    *,
    layout_mode: str = "mesa_de_luz",
    has_title: bool = False,
    has_subtitle: bool = False,
    weights: list[float] | None = None,
    page_w: float,
    page_h: float,
    margin_left: float,
    margin_right: float,
    margin_top: float,
    margin_bottom: float,
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
        page_w, page_h: Trim dimensions in points
        margin_left, margin_right, margin_top, margin_bottom: Safe insets in points.
            margin_top is the *base* top inset; TITLE_SPACE and SUBTITLE_SPACE
            are added on top when has_title/has_subtitle are set.
    """
    n = len(image_paths)
    if n == 0:
        return []

    if weights is None:
        weights = [1.0] * n

    config = LAYOUT_CONFIGS.get(layout_mode, LAYOUT_CONFIGS["mesa_de_luz"])
    rng = random.Random(seed)

    effective_margin_top = margin_top + (TITLE_SPACE if has_title else 0) + (SUBTITLE_SPACE if has_subtitle else 0)

    usable_w = page_w - margin_left - margin_right
    usable_h = page_h - effective_margin_top - margin_bottom

    # Read actual aspect ratios
    aspect_ratios = [_get_aspect_ratio(p) for p in image_paths]

    # Uniform-grid family: identical cells, weights ignored, picks the best
    # (rows × cols) divisor pair by total photo area. The "grid_fit" key in
    # the config switches between letterbox-with-large-cells (contain),
    # letterbox-with-photo-shaped-cells (compact), and crop-to-fill (cover).
    if config.get("grid_fit"):
        return _compute_uniform_grid_layout(
            image_paths, aspect_ratios, usable_w, usable_h,
            margin_left, effective_margin_top, config, rng,
        )

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
                margin_left, effective_margin_top, config, rng
            )

    # Calculate total size and center
    if is_mosaic:
        # Mosaic rects already carry absolute positions inside the usable frame.
        x_offset = 0
        y_offset = 0
    elif is_column_major:
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

    if is_mosaic:
        # Mosaic placement: hero first, then remaining; each photo placed
        # using the precomputed rect and the *original* photo index so the
        # right image lands in each region (the old code assumed photos
        # were sorted by weight, which they aren't).
        entries = [rows_or_cols["hero"]] + rows_or_cols["remaining"]
        for placement_idx, entry in enumerate(entries):
            orig_idx = entry["index"]
            rect_x, rect_y, rect_w, rect_h = entry["rect"]
            photo_path = image_paths[orig_idx]

            photo_w = rect_w
            photo_h = rect_h

            photo_w, photo_h, rotation, jitter_x, jitter_y = _rotate_and_jitter(photo_w, photo_h, config, rng)

            # Re-center the (possibly shrunk-by-rotation) photo inside its rect
            # so rotation doesn't make it cross into a neighbour's rect.
            center_offset_x = (rect_w - photo_w) / 2
            center_offset_y = (rect_h - photo_h) / 2

            x = margin_left + rect_x + center_offset_x + jitter_x
            y = effective_margin_top + rect_y + center_offset_y + jitter_y

            x, y = _clamp_to_page(x, y, photo_w, photo_h, margin_left, effective_margin_top, page_w, page_h, margin_right, margin_bottom)

            z = _interleaved_z(placement_idx, n, rng)

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
    elif is_column_major:
        # Column-major placement
        current_x = margin_left + x_offset
        for col_eff_ars, col_w in rows_or_cols:
            col_real_ars = aspect_ratios[photo_idx : photo_idx + len(col_eff_ars)]
            col_photos = image_paths[photo_idx : photo_idx + len(col_eff_ars)]

            current_y = effective_margin_top
            for photo_path, real_ar in zip(col_photos, col_real_ars):
                photo_w = col_w
                photo_h = col_w / real_ar

                photo_w, photo_h, rotation, jitter_x, jitter_y = _rotate_and_jitter(photo_w, photo_h, config, rng)

                x = current_x + jitter_x
                y = current_y + jitter_y

                x, y = _clamp_to_page(x, y, photo_w, photo_h, margin_left, effective_margin_top, page_w, page_h, margin_right, margin_bottom)

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
        current_y = effective_margin_top + y_offset
        for row_eff_ars, row_h in rows_or_cols:
            row_photos = image_paths[photo_idx : photo_idx + len(row_eff_ars)]
            row_real_ars = aspect_ratios[photo_idx : photo_idx + len(row_eff_ars)]

            actual_row_w = sum(ar * row_h for ar in row_real_ars) + BASE_GAP * (len(row_real_ars) - 1)
            x_offset_row = max(0, (usable_w - actual_row_w) / 2)
            current_x = margin_left + x_offset_row

            for i, (photo_path, real_ar) in enumerate(zip(row_photos, row_real_ars)):
                photo_w = real_ar * row_h
                photo_h = row_h

                photo_w, photo_h, rotation, jitter_x, jitter_y = _rotate_and_jitter(photo_w, photo_h, config, rng)

                x = current_x + jitter_x
                y = current_y + jitter_y

                x, y = _clamp_to_page(x, y, photo_w, photo_h, margin_left, effective_margin_top, page_w, page_h, margin_right, margin_bottom)

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

    _resolve_overlaps(placed)
    placed.sort(key=lambda p: p.z_index)
    return placed


def _pick_uniform_grid_dimensions(
    n: int,
    aspect_ratios: list[float],
    usable_w: float,
    usable_h: float,
    gap: float,
) -> tuple[int, int]:
    """Pick (rows, cols) maximizing total photo area for N photos.

    Enumerates every (rows, cols) with rows * cols == n, simulates placing
    each photo letterboxed inside its cell, and selects the configuration
    with the largest total photo area. Ties are broken by preferring the
    shape closest to square (smallest |rows - cols|).

    For prime n the only candidates are 1×n and n×1; the function still
    picks the better of the two.
    """
    candidates: list[tuple[int, int]] = []
    for rows in range(1, n + 1):
        if n % rows == 0:
            candidates.append((rows, n // rows))

    best: tuple[int, int] = (1, n)
    best_score = -1.0
    for rows, cols in candidates:
        if cols * gap >= usable_w or rows * gap >= usable_h:
            continue
        cell_w = (usable_w - (cols - 1) * gap) / cols
        cell_h = (usable_h - (rows - 1) * gap) / rows
        if cell_w <= 0 or cell_h <= 0:
            continue
        total_area = 0.0
        for ar in aspect_ratios:
            photo_w = cell_w
            photo_h = cell_w / ar
            if photo_h > cell_h:
                photo_h = cell_h
                photo_w = cell_h * ar
            total_area += photo_w * photo_h
        # Tiebreaker: prefer the shape closest to square so 6 → 3×2 wins over 6×1 ties.
        score = (total_area, -abs(rows - cols))
        if score > (best_score, 0):
            best_score = total_area
            best = (rows, cols)
    return best


def _compute_uniform_grid_layout(
    image_paths: list[Path],
    aspect_ratios: list[float],
    usable_w: float,
    usable_h: float,
    margin_left: float,
    margin_top: float,
    config: dict,
    rng: random.Random,
) -> list[PlacedPhoto]:
    """Strict N×M grid with uniform cell sizes.

    `config["grid_fit"]` selects the visual strategy:

    - ``"contain"`` (cuadricula_uniforme): cells fill the usable area; photos
      letterboxed inside cells. Inner-cell whitespace can be significant when
      the cell AR is far from the photo AR.
    - ``"compact"`` (cuadricula_compacta): cells are sized to match the photo
      AR exactly. Photos fill their cells with no inner whitespace and the
      grid as a whole is centered on the page (whitespace moves outside).
    - ``"cover"`` (cuadricula_maximizada): cells fill the usable area; photos
      are scaled to fill cells with crop. The renderer clips the overflow.
    """
    n = len(image_paths)
    rows, cols = _pick_uniform_grid_dimensions(n, aspect_ratios, usable_w, usable_h, BASE_GAP)

    fit_mode = config.get("grid_fit", "contain")
    fill_factor = config.get("fill_factor", 0.97)

    # Cell dimensions before any compact shrinking.
    base_grid_w = usable_w * fill_factor
    base_grid_h = usable_h * fill_factor
    cell_w = (base_grid_w - (cols - 1) * BASE_GAP) / cols
    cell_h = (base_grid_h - (rows - 1) * BASE_GAP) / rows

    if fit_mode == "compact":
        # Shrink each cell so its AR matches the photo AR — eliminates the
        # inner-cell whitespace. We use the average photo AR (most albums
        # are visually uniform; mixed AR pages letterbox the outliers).
        avg_ar = sum(aspect_ratios) / len(aspect_ratios)
        # Try fitting cells with AR = avg_ar inside the cell rectangle.
        target_cell_w = cell_w
        target_cell_h = cell_w / avg_ar
        if target_cell_h > cell_h:
            target_cell_h = cell_h
            target_cell_w = cell_h * avg_ar
        cell_w, cell_h = target_cell_w, target_cell_h

    grid_w = cols * cell_w + (cols - 1) * BASE_GAP
    grid_h = rows * cell_h + (rows - 1) * BASE_GAP
    x_offset = (usable_w - grid_w) / 2
    y_offset = (usable_h - grid_h) / 2

    placed: list[PlacedPhoto] = []
    for i, (photo_path, ar) in enumerate(zip(image_paths, aspect_ratios)):
        row = i // cols
        col = i % cols

        cell_x = margin_left + x_offset + col * (cell_w + BASE_GAP)
        cell_y = margin_top + y_offset + row * (cell_h + BASE_GAP)

        if fit_mode == "cover":
            # Photo occupies the full cell; the renderer crops via clip.
            photo_w = cell_w
            photo_h = cell_h
            x, y = cell_x, cell_y
            placed_fit = "cover"
        else:
            # Letterbox inside the cell, AR preserved.
            photo_w = cell_w
            photo_h = cell_w / ar
            if photo_h > cell_h:
                photo_h = cell_h
                photo_w = cell_h * ar
            x = cell_x + (cell_w - photo_w) / 2
            y = cell_y + (cell_h - photo_h) / 2
            placed_fit = "contain"

        placed.append(
            PlacedPhoto(
                path=photo_path,
                x=x,
                y=y,
                w=photo_w,
                h=photo_h,
                rotation=0.0,
                z_index=i,
                fit_mode=placed_fit,
            )
        )

    logger.debug(f"    Uniform grid {rows}x{cols} for {n} photos (fit={fit_mode})")
    return placed


def _compute_grid_layout(
    image_paths: list[Path],
    aspect_ratios: list[float],
    n: int,
    usable_w: float,
    usable_h: float,
    margin_left: float,
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

        cell_x = margin_left + x_offset + col * (cell_size + BASE_GAP)
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


def _resolve_overlaps(placed: list[PlacedPhoto], min_gap: float = BASE_GAP / 2) -> None:
    """Last-line safety net: shrink overlapping photos in place.

    The layout branches are responsible for producing non-overlapping
    placements. This helper only acts when something slipped through
    (e.g. a clamp pushed a photo into a neighbour) and it logs a
    warning so regressions surface immediately. Only shrinks around the
    photo centre — never repositions, to avoid masking real bugs.
    """
    if len(placed) < 2:
        return
    for _ in range(3):
        adjusted = False
        for i in range(len(placed)):
            for j in range(i + 1, len(placed)):
                a, b = placed[i], placed[j]
                overlap_x = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
                overlap_y = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
                if overlap_x > min_gap and overlap_y > min_gap:
                    logger.warning(
                        f"    Overlap: {a.path.name} vs {b.path.name} "
                        f"({overlap_x:.1f}pt x {overlap_y:.1f}pt) — shrinking"
                    )
                    for photo in (a, b):
                        cx = photo.x + photo.w / 2
                        cy = photo.y + photo.h / 2
                        photo.w *= 0.93
                        photo.h *= 0.93
                        photo.x = cx - photo.w / 2
                        photo.y = cy - photo.h / 2
                    adjusted = True
        if not adjusted:
            return
