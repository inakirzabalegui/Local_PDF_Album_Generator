"""Page styling: dynamic background color and photo border rendering."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import Color, white

from src.utils.color import hex_to_rgb, page_background_color, rgb_to_reportlab
from src.workspace.config import GlobalConfig, PageConfig

BORDER_PX = 4  # points


def resolve_background_color(
    page_cfg: PageConfig,
    global_cfg: GlobalConfig,
) -> Color:
    """Determine the background color for a page.

    Priority: page override > computed from images > global default.
    """
    if page_cfg.override_background_color:
        rgb = hex_to_rgb(page_cfg.override_background_color)
        r, g, b = rgb_to_reportlab(rgb)
        return Color(r, g, b)

    images = page_cfg.image_files()
    if images:
        rgb = page_background_color(images)
        r, g, b = rgb_to_reportlab(rgb)
        return Color(r, g, b)

    rgb = hex_to_rgb(global_cfg.default_background_color)
    r, g, b = rgb_to_reportlab(rgb)
    return Color(r, g, b)


def draw_photo_border(
    canvas,  # reportlab canvas
    x: float,
    y: float,
    w: float,
    h: float,
    border: float = BORDER_PX,
) -> None:
    """Draw a white rectangular border behind where a photo will be placed."""
    canvas.setFillColor(white)
    canvas.setStrokeColor(white)
    canvas.rect(
        x - border,
        y - border,
        w + 2 * border,
        h + 2 * border,
        fill=1,
        stroke=0,
    )
