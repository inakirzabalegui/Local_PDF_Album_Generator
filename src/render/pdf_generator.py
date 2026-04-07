"""PDF generation orchestrator using ReportLab."""

from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image
from reportlab.lib.colors import Color, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from src.render.covers import render_backcover, render_cover
from src.render.layout import LAYOUT_CONFIGS, PlacedPhoto, compute_layout
from src.render.styling import BORDER_PX, draw_photo_border, resolve_background_color
from src.workspace.config import GlobalConfig, PageConfig

PAGE_W, PAGE_H = A4
logger = logging.getLogger("album")

# Flag to track if fonts have been registered
_FONTS_REGISTERED = False


def _register_fonts() -> None:
    """Register TrueType fonts for proper UTF-8 support (tildes, ñ, etc.)."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    
    try:
        # Register Helvetica with UTF-8 support
        pdfmetrics.registerFont(TTFont('HelveticaUTF8', '/System/Library/Fonts/Helvetica.ttc'))
        logger.debug("Registered HelveticaUTF8 font for UTF-8 support")
        _FONTS_REGISTERED = True
    except Exception as exc:
        logger.warning(f"Could not register TrueType font: {exc}. Falling back to standard fonts.")


def generate_album(
    pages: list[PageConfig],
    cfg: GlobalConfig,
    workspace: Path,
) -> list[Path]:
    """Generate one or more PDF volumes from the workspace pages.

    Returns the list of output file paths.
    """
    # Register fonts with UTF-8 support
    _register_fonts()
    
    # Peecho printing validation: 500-page maximum (498 content + cover + backcover)
    if cfg.max_pages_per_volume > 498:
        logger.warning(
            f"max_pages_per_volume ({cfg.max_pages_per_volume}) exceeds Peecho's 500-page limit. "
            f"Recommended maximum: 498 pages (to allow for cover + backcover)."
        )
    
    content_pages = [p for p in pages if not p.is_cover and not p.is_backcover]
    cover = next((p for p in pages if p.is_cover), None)
    backcover = next((p for p in pages if p.is_backcover), None)

    volumes = _split_volumes(content_pages, cfg.max_pages_per_volume)
    output_paths: list[Path] = []

    for vol_idx, vol_pages in enumerate(volumes):
        if len(volumes) == 1:
            filename = f"{cfg.project_title}.pdf"
        else:
            filename = f"{cfg.project_title}_Vol{vol_idx + 1}.pdf"

        output = workspace / filename
        c = Canvas(str(output), pagesize=A4)

        if cover and vol_idx == 0:
            images = cover.image_files()
            if images:
                render_cover(
                    c, 
                    images[0], 
                    cfg.project_title, 
                    cfg.date_range, 
                    "HelveticaUTF8"
                )

        total = len(vol_pages)
        for i, page_cfg in enumerate(vol_pages, 1):
            print(f"\r[render]   Página {i}/{total} ...", end="", flush=True)
            _render_content_page(c, page_cfg, cfg)
        print()

        # Peecho compliance: Ensure minimum 24 pages and even page count
        pages_written = (1 if cover and vol_idx == 0 else 0) + len(vol_pages)
        has_backcover_in_volume = backcover and vol_idx == len(volumes) - 1
        
        if has_backcover_in_volume:
            pages_written += 1  # Count the backcover
        
        # Minimum 24 pages padding (Peecho requirement: 24-500 pages)
        if pages_written < 24:
            blank_pages_needed = 24 - pages_written
            logger.warning(
                f"Volume has only {pages_written} pages. Peecho requires minimum 24 pages. "
                f"Adding {blank_pages_needed} blank page(s)."
            )
            for _ in range(blank_pages_needed):
                c.setFillColor(white)
                c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
                c.showPage()
            pages_written = 24
        
        # Even page count padding (Peecho requirement: even number of pages)
        if pages_written % 2 != 0:
            logger.info("Inserting blank page to ensure even page count (Peecho requirement)")
            c.setFillColor(white)
            c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
            c.showPage()

        if backcover and vol_idx == len(volumes) - 1:
            images = backcover.image_files()
            if images:
                render_backcover(c, images[0])

        c.save()
        output_paths.append(output)

    return output_paths


def _render_content_page(
    c: Canvas,
    page_cfg: PageConfig,
    global_cfg: GlobalConfig,
) -> None:
    """Render a single content page onto the canvas."""
    logger.debug(f"Rendering page {page_cfg.page_number}: {page_cfg.photo_count} photos, mode={page_cfg.layout_mode}")
    
    bg_color = resolve_background_color(page_cfg, global_cfg)
    c.setFillColor(bg_color)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    if page_cfg.section_titles:
        _draw_section_titles(c, page_cfg.section_titles, "HelveticaUTF8")
        logger.debug(f"  Section titles: {page_cfg.section_titles}")

    images = page_cfg.image_files()
    if not images:
        logger.warning(f"  Page {page_cfg.page_number} has no images!")
        c.showPage()
        return

    # Build weights list based on photo filenames
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
    )
    
    logger.debug(f"  Layout computed: {len(placed)} photos placed")
    for i, photo in enumerate(placed[:3], 1):  # Log first 3 for debugging
        logger.debug(f"    Photo {i}: w={photo.w:.1f}pt, h={photo.h:.1f}pt, rot={photo.rotation:.2f}°")

    for photo in placed:
        c.saveState()

        center_x = photo.x + photo.w / 2
        center_y = _flip_y(photo.y + photo.h / 2)

        c.translate(center_x, center_y)
        c.rotate(photo.rotation)

        draw_x = -photo.w / 2
        draw_y = -photo.h / 2

        # Always draw white border
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
        except Exception as exc:
            c.setFillColor(Color(0.8, 0.2, 0.2))
            c.rect(draw_x, draw_y, photo.w, photo.h, fill=1, stroke=0)

        c.restoreState()

    # Draw page number
    _draw_page_number(c, page_cfg.page_number, "HelveticaUTF8")

    c.showPage()


def _draw_page_number(
    c: Canvas,
    page_number: int,
    font_name: str,
) -> None:
    """Draw page number in bottom-right corner."""
    c.saveState()
    c.setFillColor(white)
    font_size = 9
    c.setFont(font_name, font_size)
    
    text = str(page_number)
    margin = 30  # 10mm minimum margin required by Peecho printing specs
    x = PAGE_W - margin - c.stringWidth(text, font_name, font_size)
    y = margin
    
    c.drawString(x, y, text)
    c.restoreState()


def _draw_section_titles(
    c: Canvas,
    titles: list[str],
    font_name: str,
) -> None:
    """Draw section title overlays at the top of the page.
    
    First title is prominent (14pt), second title is subtle (10pt).
    """
    if not titles:
        return
    
    c.saveState()
    
    primary_title = titles[0]
    font_size_primary = 14
    bar_height_primary = 1.2 * cm
    bar_y_primary = PAGE_H - 50
    
    c.setFillColor(Color(0, 0, 0, alpha=0.4))
    c.rect(0, bar_y_primary, PAGE_W, bar_height_primary, fill=1, stroke=0)
    
    c.setFillColor(white)
    c.setFont(font_name, font_size_primary)
    text_w = c.stringWidth(primary_title, font_name, font_size_primary)
    x = (PAGE_W - text_w) / 2
    y = bar_y_primary + (bar_height_primary - font_size_primary) / 2 + 2
    c.drawString(x, y, primary_title)
    
    if len(titles) > 1:
        secondary_title = titles[1]
        font_size_secondary = 10
        bar_height_secondary = 0.8 * cm
        bar_y_secondary = bar_y_primary - bar_height_primary - 8
        
        c.setFillColor(Color(0, 0, 0, alpha=0.25))
        c.rect(0, bar_y_secondary, PAGE_W, bar_height_secondary, fill=1, stroke=0)
        
        c.setFillColor(white)
        c.setFont(font_name, font_size_secondary)
        text_w_sec = c.stringWidth(secondary_title, font_name, font_size_secondary)
        x_sec = (PAGE_W - text_w_sec) / 2
        y_sec = bar_y_secondary + (bar_height_secondary - font_size_secondary) / 2 + 2
        c.drawString(x_sec, y_sec, secondary_title)
    
    c.restoreState()


def _optimized_image_reader(path: Path, display_w: float, display_h: float) -> ImageReader:
    """Resize image in memory to match actual display size at 300 DPI.
    
    This dramatically reduces PDF file size by only embedding the pixels
    that are actually visible, not the full downsampled image.
    """
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


def _flip_y(y: float) -> float:
    """ReportLab uses bottom-left origin; our layout uses top-left."""
    return PAGE_H - y


def _split_volumes(
    pages: list[PageConfig],
    max_per_volume: int,
) -> list[list[PageConfig]]:
    """Split content pages into volume-sized chunks.
    
    Note: Peecho printing requires 24-500 pages per book. The max_per_volume
    setting should not exceed 498 (500 minus cover and backcover).
    """
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
    """Generate a PDF for a single page, saved in the page's folder.
    
    Returns the path to the generated PDF.
    """
    _register_fonts()
    
    # Nombre del PDF basado en el número de página
    filename = f"page_{page_cfg.page_number:02d}.pdf"
    output = page_cfg.folder / filename
    
    # Crear canvas
    c = Canvas(str(output), pagesize=A4)
    
    # Renderizar la página
    _render_content_page(c, page_cfg, global_cfg)
    
    # Guardar PDF
    c.save()
    
    return output
