"""Photo layout algorithms with justified row-packing collage style.

Places N photos (6–10) on an A4 canvas using justified rows for optimal space usage.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
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
                reduction = 1.0 / (math.cos(rad) + (photo_h/photo_w) * math.sin(rad))
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


def _justified_rows(
    aspect_ratios: list[float],
    usable_w: float,
    usable_h: float,
    gap: float,
    fill_factor: float,
    weights: list[float] | None = None,
) -> list[tuple[list[float], float]]:
    """Pack photos into justified rows using balanced partition.

    Returns list of (row_aspect_ratios, row_height) tuples.
    
    weights: Optional list of weight multipliers (one per photo). Weighted photos
             claim more space by using effective_ar = ar * weight.
    """
    n = len(aspect_ratios)
    if n == 0:
        return []
    
    if weights is None:
        weights = [1.0] * n
    
    # Single photo: fill most of the page
    if n == 1:
        row_h = usable_h * fill_factor
        return [(aspect_ratios, row_h)]

    # Use effective ARs for layout calculations (weighted photos appear "wider")
    effective_ars = [ar * w for ar, w in zip(aspect_ratios, weights)]

    # Try different row counts and pick best area coverage.
    # Key insight: row_h = (usable_w - gaps) / sum(effective_ARs) is the MAX height
    # that fills width exactly. Never scale UP or photos exceed page width.
    best_layout = None
    best_score = -1
    best_num_rows = 0
    
    max_rows = min(n, 4)
    min_rows = 2
    
    for num_rows in range(min_rows, max_rows + 1):
        partition = _balanced_partition(effective_ars, num_rows, weights)
        row_data: list[tuple[list[float], float]] = []
        
        for row_eff_ars in partition:
            row_h = (usable_w - gap * (len(row_eff_ars) - 1)) / sum(row_eff_ars)
            row_data.append((row_eff_ars, row_h))
        
        total_h = sum(h for _, h in row_data) + gap * (num_rows - 1)
        
        # Symmetric scoring: measures how close total_h is to usable_h.
        # Underfill: width=100%, height=partial → area ≈ total_h/usable_h
        # Overflow (needs compression): height=100%, width=partial → area ≈ usable_h/total_h
        if total_h <= usable_h:
            score = total_h / usable_h
        else:
            score = usable_h / total_h
        
        logger.debug(f"    Trying {num_rows} rows: total_h={total_h:.1f}pt, score={score:.3f}")
        
        if score > best_score:
            best_score = score
            best_layout = row_data
            best_num_rows = num_rows
    
    logger.debug(f"    Selected {best_num_rows} rows (score={best_score:.3f})")
    
    # Post-processing: NEVER scale up. Only compress if overflow.
    if best_layout:
        total_h = sum(h for _, h in best_layout) + gap * (len(best_layout) - 1)
        
        if total_h > usable_h:
            scale = usable_h / total_h
            logger.debug(f"    Compressing to fit: scale={scale:.3f}")
            best_layout = [(ars, h * scale) for ars, h in best_layout]
        else:
            logger.debug(f"    Rows fit naturally ({total_h:.1f}pt / {usable_h:.1f}pt)")
        
        for i, (ars, h) in enumerate(best_layout, 1):
            actual_w = sum(ar * h for ar in ars) + gap * (len(ars) - 1)
            logger.debug(f"    Row {i}: {len(ars)} photos, h={h:.1f}pt, row_w={actual_w:.1f}pt")
    
    return best_layout or []


def _balanced_partition(
    effective_ars: list[float],
    num_rows: int,
    weights: list[float] | None = None,
) -> list[list[float]]:
    """Distribute photos across N rows by weight sum.
    
    Weighted photos gravitate to rows with fewer neighbors, naturally becoming bigger.
    """
    n = len(effective_ars)
    if weights is None:
        weights = [1.0] * n
    
    total_weight = sum(weights)
    target_per_row = total_weight / num_rows
    
    rows: list[list[float]] = []
    current_row: list[float] = []
    current_weight = 0.0
    idx = 0
    
    for i in range(n):
        current_row.append(effective_ars[i])
        current_weight += weights[i]
        
        # Start new row if we've reached target weight (but not on last row)
        if current_weight >= target_per_row and len(rows) < num_rows - 1:
            rows.append(current_row)
            current_row = []
            current_weight = 0.0
    
    # Add remaining photos to last row
    if current_row:
        rows.append(current_row)
    
    return rows


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
