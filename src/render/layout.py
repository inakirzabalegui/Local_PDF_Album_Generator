"""Relaxed masonry layout algorithm – 'Light Table Effect'.

Places N photos (4–9) on an A4 canvas with slight randomness in position
and rotation, simulating photos scattered on a light table.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4

PAGE_W, PAGE_H = A4  # points (72 dpi)
MARGIN = 36  # 0.5 inch margin on all sides
BORDER_WIDTH = 4  # white border thickness in points
ROTATION_RANGE = 3.0  # degrees ±


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
    page_w: float = PAGE_W,
    page_h: float = PAGE_H,
    margin: float = MARGIN,
) -> list[PlacedPhoto]:
    """Compute positions for all images on a single page.

    Uses a grid-based approach with jitter for the 'light table' look.
    """
    n = len(image_paths)
    if n == 0:
        return []

    rng = random.Random(seed)

    cols, rows = _grid_dimensions(n)
    usable_w = page_w - 2 * margin
    usable_h = page_h - 2 * margin
    cell_w = usable_w / cols
    cell_h = usable_h / rows

    placed: list[PlacedPhoto] = []

    for idx, img_path in enumerate(image_paths):
        col = idx % cols
        row = idx // cols

        img_w, img_h = _image_size(img_path)
        if img_w == 0 or img_h == 0:
            img_w, img_h = 400, 300

        fit_w, fit_h = _fit_in_cell(
            img_w, img_h, cell_w * 0.88, cell_h * 0.88
        )

        base_x = margin + col * cell_w + (cell_w - fit_w) / 2
        base_y = margin + row * cell_h + (cell_h - fit_h) / 2

        jitter_x = rng.uniform(-cell_w * 0.06, cell_w * 0.06)
        jitter_y = rng.uniform(-cell_h * 0.06, cell_h * 0.06)

        x = base_x + jitter_x
        y = base_y + jitter_y

        rotation = rng.uniform(-ROTATION_RANGE, ROTATION_RANGE)

        z = _interleaved_z(idx, n, rng)

        placed.append(
            PlacedPhoto(
                path=img_path,
                x=x,
                y=y,
                w=fit_w,
                h=fit_h,
                rotation=rotation,
                z_index=z,
            )
        )

    placed.sort(key=lambda p: p.z_index)
    return placed


def _grid_dimensions(n: int) -> tuple[int, int]:
    """Choose a cols x rows grid for *n* photos."""
    layouts: dict[int, tuple[int, int]] = {
        1: (1, 1),
        2: (2, 1),
        3: (3, 1),
        4: (2, 2),
        5: (3, 2),
        6: (3, 2),
        7: (3, 3),
        8: (3, 3),
        9: (3, 3),
    }
    return layouts.get(n, (int(math.ceil(math.sqrt(n))), int(math.ceil(n / math.ceil(math.sqrt(n))))))


def _fit_in_cell(
    img_w: int, img_h: int, cell_w: float, cell_h: float
) -> tuple[float, float]:
    """Scale image to fit inside cell while preserving aspect ratio."""
    ratio = min(cell_w / img_w, cell_h / img_h)
    return img_w * ratio, img_h * ratio


def _image_size(path: Path) -> tuple[int, int]:
    """Read image dimensions without fully loading pixel data."""
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return (0, 0)


def _interleaved_z(index: int, total: int, rng: random.Random) -> int:
    """Generate a z-index that creates a natural stacking order.

    Even indices get lower z (background), odd indices get higher z (foreground),
    with a small random perturbation for realism.
    """
    base = index * 2
    return base + rng.randint(0, 1)
