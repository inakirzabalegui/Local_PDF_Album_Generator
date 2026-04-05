"""PDF generation orchestrator using ReportLab."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import Color, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from src.render.covers import render_backcover, render_cover
from src.render.layout import PlacedPhoto, compute_layout
from src.render.styling import BORDER_PX, draw_photo_border, resolve_background_color
from src.workspace.config import GlobalConfig, PageConfig

PAGE_W, PAGE_H = A4


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
                render_cover(c, images[0], cfg.project_title, cfg.typography_system_font)

        for page_cfg in vol_pages:
            _render_content_page(c, page_cfg, cfg)

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
    bg_color = resolve_background_color(page_cfg, global_cfg)
    c.setFillColor(bg_color)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    images = page_cfg.image_files()
    if not images:
        c.showPage()
        return

    placed = compute_layout(images, page_cfg.layout_seed)

    prev_group: str | None = None

    for photo in placed:
        group = _detect_source_group(photo.path)

        c.saveState()

        center_x = photo.x + photo.w / 2
        center_y = _flip_y(photo.y + photo.h / 2)

        c.translate(center_x, center_y)
        c.rotate(photo.rotation)

        draw_x = -photo.w / 2
        draw_y = -photo.h / 2

        draw_photo_border(c, draw_x, draw_y, photo.w, photo.h, BORDER_PX)

        try:
            reader = ImageReader(str(photo.path))
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

        if prev_group is not None and group != prev_group:
            _draw_group_label(c, group, photo, global_cfg.typography_system_font)
        prev_group = group

    c.showPage()


def _draw_group_label(
    c: Canvas,
    group_name: str,
    photo: PlacedPhoto,
    font_name: str,
) -> None:
    """Draw a semi-transparent label indicating a directory transition."""
    c.saveState()
    font_size = 8
    c.setFont(font_name, font_size)

    label_x = photo.x
    label_y = _flip_y(photo.y) + 6

    c.setFillColor(Color(1, 1, 1, alpha=0.7))
    text_w = c.stringWidth(group_name, font_name, font_size)
    c.rect(label_x - 2, label_y - 2, text_w + 4, font_size + 4, fill=1, stroke=0)

    c.setFillColor(Color(0.2, 0.2, 0.2))
    c.drawString(label_x, label_y, group_name)
    c.restoreState()


def _flip_y(y: float) -> float:
    """ReportLab uses bottom-left origin; our layout uses top-left."""
    return PAGE_H - y


def _detect_source_group(path: Path) -> str:
    """Infer source group from the page folder name."""
    return path.parent.name


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
