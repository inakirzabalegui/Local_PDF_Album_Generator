"""Cover and back-cover rendering with center-crop bleed."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import white, Color

PAGE_W, PAGE_H = A4


def render_cover(
    canvas,  # reportlab canvas
    image_path: Path,
    title: str,
    date_range: str = "",
    font_name: str = "Helvetica",
) -> None:
    """Render a full-bleed cover page with center-cropped image and title overlay."""
    _draw_bleed_image(canvas, image_path)
    _draw_title_overlay(canvas, title, date_range, font_name)
    canvas.showPage()


def render_backcover(
    canvas,  # reportlab canvas
    image_path: Path,
) -> None:
    """Render a full-bleed back cover page with center-cropped image."""
    _draw_bleed_image(canvas, image_path)
    canvas.showPage()


def _draw_bleed_image(canvas, image_path: Path) -> None:
    """Center-crop and draw an image filling the entire A4 page."""
    cropped = _center_crop_to_ratio(image_path, PAGE_W / PAGE_H)

    from reportlab.lib.utils import ImageReader
    reader = ImageReader(cropped)
    canvas.drawImage(reader, 0, 0, width=PAGE_W, height=PAGE_H)


def _draw_title_overlay(
    canvas,
    title: str,
    date_range: str,
    font_name: str,
) -> None:
    """Draw two bands: thick band with title (top third) and thin band with dates (bottom third)."""
    canvas.saveState()
    
    # 10mm minimum margin required by Peecho printing specs
    SAFE_MARGIN = 29

    thick_bar_h = 3.0 * cm
    thick_bar_y = PAGE_H * 0.70
    
    canvas.setFillColor(Color(0, 0, 0, alpha=0.5))
    canvas.rect(0, thick_bar_y, PAGE_W, thick_bar_h, fill=1, stroke=0)
    
    canvas.setFillColor(white)
    font_size_title = 36
    canvas.setFont(font_name, font_size_title)
    text_w = canvas.stringWidth(title, font_name, font_size_title)
    x = (PAGE_W - text_w) / 2
    # Ensure title respects minimum margin (for very long titles)
    x = max(SAFE_MARGIN, min(x, PAGE_W - SAFE_MARGIN - text_w))
    y = thick_bar_y + (thick_bar_h - font_size_title) / 2 + 6
    canvas.drawString(x, y, title)

    if date_range:
        thin_bar_h = 1.2 * cm
        thin_bar_y = PAGE_H * 0.12
        
        canvas.setFillColor(Color(0, 0, 0, alpha=0.35))
        canvas.rect(0, thin_bar_y, PAGE_W, thin_bar_h, fill=1, stroke=0)
        
        canvas.setFillColor(white)
        font_size_date = 16
        canvas.setFont(font_name, font_size_date)
        text_w_date = canvas.stringWidth(date_range, font_name, font_size_date)
        x_date = (PAGE_W - text_w_date) / 2
        # Ensure date respects minimum margin
        x_date = max(SAFE_MARGIN, min(x_date, PAGE_W - SAFE_MARGIN - text_w_date))
        y_date = thin_bar_y + (thin_bar_h - font_size_date) / 2 + 2
        canvas.drawString(x_date, y_date, date_range)

    canvas.restoreState()


def _center_crop_to_ratio(image_path: Path, target_ratio: float) -> Image.Image:
    """Open image and center-crop it to match *target_ratio* (w/h)."""
    img = Image.open(image_path)

    from PIL import ImageOps
    img = ImageOps.exif_transpose(img)  # type: ignore[assignment]

    w, h = img.size
    current_ratio = w / h

    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    elif current_ratio < target_ratio:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    return img
