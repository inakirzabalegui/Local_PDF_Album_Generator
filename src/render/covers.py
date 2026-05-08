"""Cover and back-cover rendering.

Two modes:
  * Embedded (legacy Peecho): cover/backcover are full-bleed pages inside
    the content PDF. Sized identically to a content page.
  * Wraparound (Blurb): cover is a separate, wide PDF spanning back-flap |
    hinge | back | spine | front | hinge | front-flap, plus uniform bleed.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps
from reportlab.lib.colors import white, Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from src.printing.provider import CM_TO_PT, CoverSpec, PageSpec


# ─────────────────────────────────────────────────────────────────────────────
# Embedded cover (legacy)
# ─────────────────────────────────────────────────────────────────────────────


def render_cover(
    canvas,
    image_path: Path,
    title: str,
    date_range: str,
    font_name: str,
    spec: PageSpec,
) -> None:
    """Render a full-bleed cover page (embedded mode)."""
    pdf_w = spec.pdf_w_pt()
    pdf_h = spec.pdf_h_pt()
    safe_margin = spec.safe_inset_outside_cm * CM_TO_PT
    _draw_bleed_image(canvas, image_path, pdf_w, pdf_h)
    _draw_title_overlay(canvas, title, date_range, font_name, pdf_w, pdf_h, safe_margin)
    canvas.showPage()


def render_backcover(
    canvas,
    image_path: Path,
    spec: PageSpec,
) -> None:
    """Render a full-bleed back cover page (embedded mode)."""
    pdf_w = spec.pdf_w_pt()
    pdf_h = spec.pdf_h_pt()
    _draw_bleed_image(canvas, image_path, pdf_w, pdf_h)
    canvas.showPage()


def _draw_bleed_image(canvas, image_path: Path, pdf_w: float, pdf_h: float) -> None:
    cropped = _center_crop_to_ratio(image_path, pdf_w / pdf_h)
    reader = ImageReader(cropped)
    canvas.drawImage(reader, 0, 0, width=pdf_w, height=pdf_h)


def _draw_title_overlay(
    canvas,
    title: str,
    date_range: str,
    font_name: str,
    pdf_w: float,
    pdf_h: float,
    safe_margin: float,
) -> None:
    """Two bands overlay (thick title band + thin date band)."""
    from reportlab.lib.units import cm

    canvas.saveState()

    thick_bar_h = 3.0 * cm
    thick_bar_y = pdf_h * 0.70

    canvas.setFillColor(Color(0, 0, 0, alpha=0.5))
    canvas.rect(0, thick_bar_y, pdf_w, thick_bar_h, fill=1, stroke=0)

    canvas.setFillColor(white)
    font_size_title = 36
    canvas.setFont(font_name, font_size_title)
    text_w = canvas.stringWidth(title, font_name, font_size_title)
    x = (pdf_w - text_w) / 2
    x = max(safe_margin, min(x, pdf_w - safe_margin - text_w))
    y = thick_bar_y + (thick_bar_h - font_size_title) / 2 + 6
    canvas.drawString(x, y, title)

    if date_range:
        thin_bar_h = 1.2 * cm
        thin_bar_y = pdf_h * 0.12

        canvas.setFillColor(Color(0, 0, 0, alpha=0.35))
        canvas.rect(0, thin_bar_y, pdf_w, thin_bar_h, fill=1, stroke=0)

        canvas.setFillColor(white)
        font_size_date = 16
        canvas.setFont(font_name, font_size_date)
        text_w_date = canvas.stringWidth(date_range, font_name, font_size_date)
        x_date = (pdf_w - text_w_date) / 2
        x_date = max(safe_margin, min(x_date, pdf_w - safe_margin - text_w_date))
        y_date = thin_bar_y + (thin_bar_h - font_size_date) / 2 + 2
        canvas.drawString(x_date, y_date, date_range)

    canvas.restoreState()


def _center_crop_to_ratio(image_path: Path, target_ratio: float) -> Image.Image:
    """Open image and center-crop it to match target_ratio (w/h)."""
    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img)

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


# ─────────────────────────────────────────────────────────────────────────────
# Wraparound cover (Blurb / hardcover dust jacket)
# ─────────────────────────────────────────────────────────────────────────────


def render_wraparound_cover_pdf(
    output: Path,
    front_image: Path,
    back_image: Path,
    title: str,
    date_range: str,
    font_name: str,
    spec: CoverSpec,
) -> Path:
    """Render a single wraparound cover PDF.

    Layout (left → right inside the trim area):
        flap_back | hinge | back_cover | spine | front_cover | hinge | flap_front

    Uniform bleed `spec.bleed_cm` extends past trim on all 4 sides.
    Title overlay is restricted to the front-cover region.
    """
    from reportlab.lib.units import cm

    pdf_w = spec.pdf_w_pt()
    pdf_h = spec.pdf_h_pt()
    bleed_pt = spec.bleed_cm * CM_TO_PT
    trim_w = spec.trim_w_pt()
    trim_h = spec.trim_h_pt()

    flap = spec.flap_w_cm * CM_TO_PT
    hinge = spec.hinge_w_cm * CM_TO_PT
    spine = spec.spine_w_cm * CM_TO_PT
    side_cover_w = (trim_w - 2 * flap - 2 * hinge - spine) / 2
    side_cover_w = max(0.0, side_cover_w)

    safe = spec.safe_inset_cm * CM_TO_PT

    # x-coordinates of region boundaries inside trim space (origin at trim corner).
    x_flap_back_start = 0.0
    x_back_start = flap + hinge
    x_spine_start = x_back_start + side_cover_w
    x_front_start = x_spine_start + spine
    x_flap_front_start = x_front_start + side_cover_w + hinge
    x_trim_end = x_flap_front_start + flap  # == trim_w (by construction)

    c = Canvas(str(output), pagesize=(pdf_w, pdf_h))
    c.saveState()
    c.translate(bleed_pt, bleed_pt)  # origin → trim corner

    # Background: black so any rounding gap reads as paper edge, not bleed-through.
    c.setFillColor(white)
    c.rect(-bleed_pt, -bleed_pt, pdf_w, pdf_h, fill=1, stroke=0)

    # Back cover image (covers the whole left half: flap_back + hinge + back_cover).
    back_region_w = x_spine_start - x_flap_back_start  # spans flap+hinge+back
    if back_region_w > 0 and trim_h > 0:
        try:
            back_cropped = _center_crop_to_ratio(back_image, back_region_w / trim_h)
            reader = ImageReader(back_cropped)
            # Extend image by bleed on the left, top, bottom (outer edges).
            c.drawImage(
                reader,
                -bleed_pt,
                -bleed_pt,
                width=back_region_w + bleed_pt,
                height=trim_h + 2 * bleed_pt,
            )
        except Exception:
            pass

    # Front cover image (right half: front_cover + hinge + front_flap).
    front_region_x = x_front_start
    front_region_w = x_trim_end - front_region_x
    if front_region_w > 0 and trim_h > 0:
        try:
            front_cropped = _center_crop_to_ratio(front_image, front_region_w / trim_h)
            reader = ImageReader(front_cropped)
            c.drawImage(
                reader,
                front_region_x,
                -bleed_pt,
                width=front_region_w + bleed_pt,
                height=trim_h + 2 * bleed_pt,
            )
        except Exception:
            pass

    # Spine: uniform dark band. Could be themed later.
    if spine > 0:
        c.setFillColor(Color(0, 0, 0, alpha=0.85))
        c.rect(x_spine_start, -bleed_pt, spine, trim_h + 2 * bleed_pt, fill=1, stroke=0)

    # Title overlay restricted to front cover region.
    front_cover_x = x_front_start
    front_cover_w = side_cover_w
    if front_cover_w > 0:
        thick_bar_h = 3.0 * cm
        thick_bar_y = trim_h * 0.70
        c.setFillColor(Color(0, 0, 0, alpha=0.5))
        c.rect(front_cover_x, thick_bar_y, front_cover_w, thick_bar_h, fill=1, stroke=0)

        c.setFillColor(white)
        font_size_title = 36
        c.setFont(font_name, font_size_title)
        text_w = c.stringWidth(title, font_name, font_size_title)
        x_title = front_cover_x + (front_cover_w - text_w) / 2
        x_title = max(front_cover_x + safe, min(x_title, front_cover_x + front_cover_w - safe - text_w))
        y_title = thick_bar_y + (thick_bar_h - font_size_title) / 2 + 6
        c.drawString(x_title, y_title, title)

        if date_range:
            thin_bar_h = 1.2 * cm
            thin_bar_y = trim_h * 0.12
            c.setFillColor(Color(0, 0, 0, alpha=0.35))
            c.rect(front_cover_x, thin_bar_y, front_cover_w, thin_bar_h, fill=1, stroke=0)

            c.setFillColor(white)
            font_size_date = 16
            c.setFont(font_name, font_size_date)
            text_w_date = c.stringWidth(date_range, font_name, font_size_date)
            x_date = front_cover_x + (front_cover_w - text_w_date) / 2
            x_date = max(
                front_cover_x + safe,
                min(x_date, front_cover_x + front_cover_w - safe - text_w_date),
            )
            y_date = thin_bar_y + (thin_bar_h - font_size_date) / 2 + 2
            c.drawString(x_date, y_date, date_range)

    c.restoreState()
    c.showPage()
    c.save()

    return output
