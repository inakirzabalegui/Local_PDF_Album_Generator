"""PDF generation orchestrator using ReportLab.

Pages are rendered in a coordinate system anchored at the trim corner: a
single `c.translate(bleed_left, bleed_bottom)` per page makes the layout
algorithm bleed-agnostic. Backgrounds are drawn from negative coordinates
to fill the bleed area.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image
from reportlab.lib.colors import Color, black, white
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from src.printing.provider import CM_TO_PT, PageSpec
from src.render.covers import render_backcover, render_cover
from src.render.layout import LAYOUT_CONFIGS, PlacedPhoto, compute_layout
from src.render.styling import BORDER_PX, draw_photo_border, resolve_background_color
from src.workspace.config import GlobalConfig, PageConfig

logger = logging.getLogger("album")

# Font name used throughout; updated to fallback if TrueType registration fails
FONT_NAME = "HelveticaUTF8"

# Flag to track if fonts have been registered
_FONTS_REGISTERED = False


def _register_fonts() -> None:
    """Register TrueType fonts for proper UTF-8 support (tildes, ñ, etc.)."""
    global _FONTS_REGISTERED, FONT_NAME
    if _FONTS_REGISTERED:
        return

    try:
        pdfmetrics.registerFont(TTFont('HelveticaUTF8', '/System/Library/Fonts/Helvetica.ttc'))
        logger.debug("Registered HelveticaUTF8 font for UTF-8 support")
        FONT_NAME = "HelveticaUTF8"
        _FONTS_REGISTERED = True
    except Exception as exc:
        logger.warning(f"Could not register TrueType font: {exc}. Falling back to Helvetica.")
        FONT_NAME = "Helvetica"
        _FONTS_REGISTERED = True


# ── Geometry helpers ─────────────────────────────────────────────────────────


def _is_left_page(page_number: int, binding_side_for_odd: str) -> bool:
    """A "left page" sits on the left side of the open spread.

    With Western LTR convention, page 1 is right-hand (no facing page on left).
    binding_side_for_odd="left" means odd pages have their binding on the LEFT,
    i.e. odd pages are right-hand pages, even pages are left-hand pages.
    """
    odd_is_right = (binding_side_for_odd or "left").lower() == "left"
    odd = page_number % 2 == 1
    if odd_is_right:
        return not odd  # even pages are left-hand
    return odd


def _page_margins_pt(spec: PageSpec, is_left_page: bool) -> tuple[float, float, float, float]:
    """Return (margin_left, margin_right, margin_top, margin_bottom) in points.

    Binding edge gets safe_inset_binding; outside edge gets safe_inset_outside.
    """
    outside = spec.safe_inset_outside_cm * CM_TO_PT
    binding = spec.safe_inset_binding_cm * CM_TO_PT
    top = spec.safe_inset_top_cm * CM_TO_PT
    bottom = spec.safe_inset_bottom_cm * CM_TO_PT

    if is_left_page:
        return outside, binding, top, bottom  # binding on right
    return binding, outside, top, bottom  # binding on left


def _bleed_offsets_pt(spec: PageSpec, is_left_page: bool) -> tuple[float, float]:
    """Return (bleed_left_pt, bleed_bottom_pt) — how much to translate origin.

    Outside edge has bleed; binding edge has bleed_inside (typically 0).
    """
    outside = spec.bleed_outside_cm * CM_TO_PT
    inside = spec.bleed_inside_cm * CM_TO_PT
    bottom = spec.bleed_bottom_cm * CM_TO_PT
    if is_left_page:
        return outside, bottom  # outside on left
    return inside, bottom  # binding on left → inside bleed (=0) on left


def _pdf_page_size_pt(spec: PageSpec) -> tuple[float, float]:
    return spec.pdf_w_pt(), spec.pdf_h_pt()


# ── Album generation ─────────────────────────────────────────────────────────


def generate_album(
    pages: list[PageConfig],
    cfg: GlobalConfig,
    workspace: Path,
) -> list[Path]:
    """Generate one or more PDF volumes from the workspace pages.

    Returns the list of output file paths.
    """
    _register_fonts()

    spec = cfg.page_spec
    pdf_w, pdf_h = _pdf_page_size_pt(spec)

    if cfg.max_pages_per_volume > spec.max_pages:
        logger.warning(
            f"max_pages_per_volume ({cfg.max_pages_per_volume}) excede el límite "
            f"del proveedor ({spec.max_pages})."
        )

    content_pages = [p for p in pages if not p.is_cover and not p.is_backcover]
    cover = next((p for p in pages if p.is_cover), None)
    backcover = next((p for p in pages if p.is_backcover), None)

    volumes = _split_volumes(content_pages, cfg.max_pages_per_volume)
    output_paths: list[Path] = []

    embedded_cover = cfg.supports_embedded_cover()

    for vol_idx, vol_pages in enumerate(volumes):
        if len(volumes) == 1:
            filename = f"{cfg.project_title}.pdf"
        else:
            filename = f"{cfg.project_title}_Vol{vol_idx + 1}.pdf"

        output = workspace / filename
        c = Canvas(str(output), pagesize=(pdf_w, pdf_h))

        if embedded_cover and cover and vol_idx == 0:
            images = cover.image_files()
            if images:
                render_cover(
                    c,
                    images[0],
                    cfg.project_title,
                    cfg.date_range,
                    FONT_NAME,
                    spec,
                )

        total = len(vol_pages)
        for i, page_cfg in enumerate(vol_pages, 1):
            logger.info(f"Página {i}/{total} ...")
            _render_content_page(c, page_cfg, cfg)

        # Compliance: minimum pages and even page count
        pages_written = (1 if (embedded_cover and cover and vol_idx == 0) else 0) + len(vol_pages)
        has_backcover_in_volume = embedded_cover and backcover and vol_idx == len(volumes) - 1

        if has_backcover_in_volume:
            pages_written += 1

        min_pages = spec.min_pages
        if min_pages is not None and pages_written < min_pages:
            blank_pages_needed = min_pages - pages_written
            logger.warning(
                f"Volumen tiene {pages_written} páginas. El proveedor requiere mínimo {min_pages}. "
                f"Añadiendo {blank_pages_needed} página(s) en blanco."
            )
            for _ in range(blank_pages_needed):
                c.setFillColor(white)
                c.rect(0, 0, pdf_w, pdf_h, fill=1, stroke=0)
                c.showPage()
            pages_written = min_pages

        if pages_written % 2 != 0:
            logger.info("Insertando página en blanco para mantener conteo par.")
            c.setFillColor(white)
            c.rect(0, 0, pdf_w, pdf_h, fill=1, stroke=0)
            c.showPage()
            pages_written += 1

        if embedded_cover and backcover and vol_idx == len(volumes) - 1:
            images = backcover.image_files()
            if images:
                render_backcover(c, images[0], spec)

        c.save()
        output_paths.append(output)

    # Wraparound cover (Phase 5): generate separate cover PDF when supported.
    if not embedded_cover and (cover or backcover):
        try:
            from src.render.covers import render_wraparound_cover_pdf
        except ImportError:
            render_wraparound_cover_pdf = None

        if render_wraparound_cover_pdf is not None:
            for vol_idx, vol_pages in enumerate(volumes):
                # Cover only on first volume; backcover only on last.
                if cover and vol_idx == 0:
                    pages_in_vol = len(vol_pages)
                    if pages_in_vol % 2 != 0:
                        pages_in_vol += 1
                    cover_spec = cfg.cover_spec(pages_in_vol)
                    front_imgs = cover.image_files() if cover else []
                    back_imgs = backcover.image_files() if backcover else front_imgs
                    if front_imgs:
                        cover_filename = (
                            f"{cfg.project_title}_cover.pdf"
                            if len(volumes) == 1
                            else f"{cfg.project_title}_Vol{vol_idx + 1}_cover.pdf"
                        )
                        cover_output = workspace / cover_filename
                        render_wraparound_cover_pdf(
                            cover_output,
                            front_imgs[0],
                            back_imgs[0] if back_imgs else front_imgs[0],
                            cfg.project_title,
                            cfg.date_range,
                            FONT_NAME,
                            cover_spec,
                        )
                        output_paths.append(cover_output)

    # Clean up per-page preview PDFs after full album render completes
    logger.info("Limpiando PDFs de previsualización por página...")
    for page in content_pages:
        for preview_pdf in page.folder.glob("page_*.pdf"):
            try:
                preview_pdf.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete preview PDF {preview_pdf}: {e}")

    if cover:
        for preview_pdf in cover.folder.glob("page_*.pdf"):
            try:
                preview_pdf.unlink()
            except Exception:
                pass

    if backcover:
        for preview_pdf in backcover.folder.glob("page_*.pdf"):
            try:
                preview_pdf.unlink()
            except Exception:
                pass

    return output_paths


def _render_content_page(
    c: Canvas,
    page_cfg: PageConfig,
    global_cfg: GlobalConfig,
) -> None:
    """Render a single content page onto the canvas."""
    spec = global_cfg.page_spec
    pdf_w, pdf_h = _pdf_page_size_pt(spec)
    is_left = _is_left_page(page_cfg.page_number, global_cfg.overrides.rendering.binding_side_for_odd)
    margin_left, margin_right, margin_top, margin_bottom = _page_margins_pt(spec, is_left)
    bleed_left, bleed_bottom = _bleed_offsets_pt(spec, is_left)
    trim_w = spec.trim_w_pt()
    trim_h = spec.trim_h_pt()

    logger.debug(
        f"Rendering page {page_cfg.page_number}: {page_cfg.photo_count} photos, "
        f"mode={page_cfg.layout_mode}, left_page={is_left}"
    )

    c.saveState()
    # Anchor origin at trim corner. Layout coords now operate in trim space.
    c.translate(bleed_left, bleed_bottom)

    # Background fills full PDF page (including bleed) — drawn in negative coords.
    bg_color = resolve_background_color(page_cfg, global_cfg)
    c.setFillColor(bg_color)
    c.rect(-bleed_left, -bleed_bottom, pdf_w, pdf_h, fill=1, stroke=0)

    if page_cfg.section_titles:
        _draw_section_titles(c, page_cfg.section_titles, FONT_NAME, trim_w, trim_h)
        logger.debug(f"  Section titles: {page_cfg.section_titles}")

    images = page_cfg.image_files()
    if not images:
        logger.warning(f"  Page {page_cfg.page_number} has no images!")
        c.restoreState()
        c.showPage()
        return

    weights = [page_cfg.get_photo_weight(img.name, global_cfg) for img in images]

    has_title = bool(page_cfg.section_titles)
    has_subtitle = len(page_cfg.section_titles) > 1
    placed = compute_layout(
        images,
        page_cfg.layout_seed,
        layout_mode=page_cfg.layout_mode,
        has_title=has_title,
        has_subtitle=has_subtitle,
        weights=weights,
        page_w=trim_w,
        page_h=trim_h,
        margin_left=margin_left,
        margin_right=margin_right,
        margin_top=margin_top,
        margin_bottom=margin_bottom,
    )

    logger.debug(f"  Layout computed: {len(placed)} photos placed")

    for photo in placed:
        c.saveState()

        center_x = photo.x + photo.w / 2
        center_y = _flip_y(photo.y + photo.h / 2, trim_h)

        c.translate(center_x, center_y)
        c.rotate(photo.rotation)

        draw_x = -photo.w / 2
        draw_y = -photo.h / 2

        draw_photo_border(c, draw_x, draw_y, photo.w, photo.h, BORDER_PX)

        try:
            reader = _optimized_image_reader(photo.path, photo.w, photo.h)
            c.drawImage(
                reader,
                draw_x,
                draw_y,
                width=photo.w,
                height=photo.h,
                preserveAspectRatio=True,
            )
        except Exception:
            c.setFillColor(Color(0.8, 0.2, 0.2))
            c.rect(draw_x, draw_y, photo.w, photo.h, fill=1, stroke=0)

        c.restoreState()

        caption = page_cfg.photo_captions.get(photo.path.name)
        if caption:
            _draw_photo_caption(
                c,
                photo,
                caption,
                FONT_NAME,
                trim_w,
                trim_h,
                margin_left,
                margin_right,
                margin_bottom,
            )

    _draw_page_number(c, page_cfg.page_number, FONT_NAME, trim_w, margin_left, margin_right, margin_bottom)

    c.restoreState()
    c.showPage()


def _draw_page_number(
    c: Canvas,
    page_number: int,
    font_name: str,
    trim_w: float,
    margin_left: float,
    margin_right: float,
    margin_bottom: float,
) -> None:
    """Draw page number near the outside-bottom corner of the trim area."""
    c.saveState()
    c.setFillColor(white)
    font_size = 9
    c.setFont(font_name, font_size)

    text = str(page_number)
    text_w = c.stringWidth(text, font_name, font_size)
    # Anchor on the outside (right-margin) edge of the trim.
    x = trim_w - margin_right - text_w
    y = margin_bottom
    c.drawString(x, y, text)
    c.restoreState()


def _draw_photo_caption(
    c: Canvas,
    photo: PlacedPhoto,
    caption: str,
    font_name: str,
    trim_w: float,
    trim_h: float,
    margin_left: float,
    margin_right: float,
    margin_bottom: float,
) -> None:
    """Draw caption text below a photo."""
    if not caption:
        return

    c.saveState()

    font_size = 8
    padding = 4

    c.setFont(font_name, font_size)
    c.setFillColor(black)  # 100% K — Blurb requirement for body text

    caption_x = photo.x + photo.w / 2
    caption_y = _flip_y(photo.y, trim_h) - padding - font_size

    text_width = c.stringWidth(caption, font_name, font_size)
    caption_x -= text_width / 2

    if caption_x < margin_left:
        caption_x = margin_left
    elif caption_x + text_width > trim_w - margin_right:
        caption_x = trim_w - margin_right - text_width

    if caption_y > margin_bottom:
        c.drawString(caption_x, caption_y, caption)

    c.restoreState()


def _draw_section_titles(
    c: Canvas,
    titles: list[str],
    font_name: str,
    trim_w: float,
    trim_h: float,
) -> None:
    """Draw section title overlays at the top of the trim area."""
    if not titles:
        return

    from reportlab.lib.units import cm

    c.saveState()

    primary_title = titles[0]
    font_size_primary = 14
    bar_height_primary = 1.2 * cm
    bar_y_primary = trim_h - 50

    c.setFillColor(Color(0, 0, 0, alpha=0.4))
    c.rect(0, bar_y_primary, trim_w, bar_height_primary, fill=1, stroke=0)

    c.setFillColor(white)
    c.setFont(font_name, font_size_primary)
    text_w = c.stringWidth(primary_title, font_name, font_size_primary)
    x = (trim_w - text_w) / 2
    y = bar_y_primary + (bar_height_primary - font_size_primary) / 2 + 2
    c.drawString(x, y, primary_title)

    if len(titles) > 1:
        secondary_title = titles[1]
        font_size_secondary = 12
        bar_height_secondary = 1.0 * cm
        bar_y_secondary = bar_y_primary - bar_height_primary - 2

        c.setFillColor(Color(0, 0, 0, alpha=0.25))
        c.rect(0, bar_y_secondary, trim_w, bar_height_secondary, fill=1, stroke=0)

        c.setFillColor(white)
        c.setFont(font_name, font_size_secondary)
        text_w_sec = c.stringWidth(secondary_title, font_name, font_size_secondary)
        x_sec = (trim_w - text_w_sec) / 2
        y_sec = bar_y_secondary + (bar_height_secondary - font_size_secondary) / 2 + 2
        c.drawString(x_sec, y_sec, secondary_title)

    c.restoreState()


def _optimized_image_reader(path: Path, display_w: float, display_h: float) -> ImageReader:
    """Resize image in memory to match actual display size at 300 DPI."""
    target_w = int(display_w / 72 * 300)
    target_h = int(display_h / 72 * 300)

    img = Image.open(path)
    img.thumbnail((target_w, target_h), Image.LANCZOS)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    buf.seek(0)

    return ImageReader(buf)


def _flip_y(y: float, page_h: float) -> float:
    """ReportLab uses bottom-left origin; layout uses top-left."""
    return page_h - y


def _split_volumes(
    pages: list[PageConfig],
    max_per_volume: int,
) -> list[list[PageConfig]]:
    """Split content pages into volume-sized chunks."""
    if not pages:
        return [[]]
    volumes: list[list[PageConfig]] = []
    for i in range(0, len(pages), max_per_volume):
        volumes.append(pages[i : i + max_per_volume])
    return volumes


def generate_single_page_pdf(
    page_cfg: PageConfig,
    global_cfg: GlobalConfig,
) -> Path:
    """Generate a PDF for a single page, saved in the page's folder."""
    _register_fonts()

    filename = f"page_{page_cfg.page_number:02d}.pdf"
    output = page_cfg.folder / filename

    spec = global_cfg.page_spec
    pdf_w, pdf_h = _pdf_page_size_pt(spec)
    c = Canvas(str(output), pagesize=(pdf_w, pdf_h))

    _render_content_page(c, page_cfg, global_cfg)

    c.save()

    return output
