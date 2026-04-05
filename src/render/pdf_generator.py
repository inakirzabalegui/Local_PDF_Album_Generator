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

from src.render.covers import render_backcover, render_cover
from src.render.layout import LAYOUT_CONFIGS, PlacedPhoto, compute_layout
from src.render.styling import BORDER_PX, draw_photo_border, resolve_background_color
from src.workspace.config import GlobalConfig, PageConfig

PAGE_W, PAGE_H = A4
logger = logging.getLogger("album")


def generate_album(
    pages: list[PageConfig],
    cfg: GlobalConfig,
    workspace: Path,
) -> list[Path]:
    """Generate one or more PDF volumes from the workspace pages.

    Returns the list of output file paths.
    """
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
                    cfg.typography_system_font
                )

        total = len(vol_pages)
        for i, page_cfg in enumerate(vol_pages, 1):
            print(f"\r[render]   Página {i}/{total} ...", end="", flush=True)
            _render_content_page(c, page_cfg, cfg)
        print()

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
        _draw_section_titles(c, page_cfg.section_titles, global_cfg.typography_system_font)
        logger.debug(f"  Section titles: {page_cfg.section_titles}")

    images = page_cfg.image_files()
    if not images:
        logger.warning(f"  Page {page_cfg.page_number} has no images!")
        c.showPage()
        return

    has_title = bool(page_cfg.section_titles)
    placed = compute_layout(
        images, 
        page_cfg.layout_seed, 
        layout_mode=page_cfg.layout_mode,
        has_title=has_title,
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
    _draw_page_number(c, page_cfg.page_number, global_cfg.typography_system_font)

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
    margin = 20  # 20pt from edge
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
    """Split content pages into volume-sized chunks."""
    if not pages:
        return [[]]
    volumes: list[list[PageConfig]] = []
    for i in range(0, len(pages), max_per_volume):
        volumes.append(pages[i : i + max_per_volume])
    return volumes
