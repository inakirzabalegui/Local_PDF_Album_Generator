"""Generate app icon matching the album editor's aesthetic."""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

# App color palette
INK = (26, 24, 20)        # #1a1814
PAPER = (241, 236, 225)   # #f1ece1
VERMILION = (193, 74, 44) # #c14a2c
CREAM_DIM = (180, 172, 158)


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    s = size
    p = max(1, int(s * 0.07))
    r = int(s * 0.18)

    # Background rounded rect
    d.rounded_rectangle([p, p, s - p, s - p], radius=r, fill=INK)

    # Book dimensions — centered, slightly landscape
    bx = int(s * 0.14)
    by = int(s * 0.18)
    bw = s - 2 * bx
    bh = int(bw * 0.70)
    spine_gap = max(1, int(s * 0.025))
    page_w = (bw - spine_gap) // 2
    pr = max(1, int(s * 0.03))

    lx0, lx1 = bx, bx + page_w
    rx0, rx1 = bx + page_w + spine_gap, bx + bw
    page_color = (230, 222, 208)

    # Page shadows
    shadow = (15, 14, 12)
    off = max(1, int(s * 0.015))
    d.rounded_rectangle([lx0 + off, by + off, lx1 + off, by + bh + off], radius=pr, fill=shadow)
    d.rounded_rectangle([rx0 + off, by + off, rx1 + off, by + bh + off], radius=pr, fill=shadow)

    # Pages
    d.rounded_rectangle([lx0, by, lx1, by + bh], radius=pr, fill=page_color)
    d.rounded_rectangle([rx0, by, rx1, by + bh], radius=pr, fill=page_color)

    # Left page: grid of 3 photo thumbnails
    photo_margin = int(s * 0.06)
    ph_w = int(page_w * 0.75)
    ph_x = lx0 + (page_w - ph_w) // 2

    photos = [
        ((ph_x, by + photo_margin, ph_x + ph_w, by + photo_margin + int(bh * 0.28)), VERMILION),
        ((ph_x, by + photo_margin + int(bh * 0.32), ph_x + ph_w, by + photo_margin + int(bh * 0.57)), CREAM_DIM),
        ((ph_x, by + photo_margin + int(bh * 0.62), ph_x + ph_w, by + bh - photo_margin), (140, 130, 118)),
    ]
    for (x0, y0, x1, y1), color in photos:
        if x1 > x0 and y1 > y0:
            d.rounded_rectangle([x0, y0, x1, y1], radius=max(1, pr // 2), fill=color)

    # Right page: title lines (text simulation)
    line_x0 = rx0 + int(page_w * 0.12)
    line_x1 = rx1 - int(page_w * 0.10)
    lh = max(1, int(s * 0.022))
    line_gap = int(s * 0.038)
    line_y = by + int(bh * 0.18)
    line_colors = [INK, CREAM_DIM, CREAM_DIM, (160, 150, 138)]
    line_widths = [1.0, 0.75, 0.75, 0.50]

    for i, (lc, lw) in enumerate(zip(line_colors, line_widths)):
        y0 = line_y + i * (lh + line_gap)
        y1 = y0 + lh
        x1 = line_x0 + int((line_x1 - line_x0) * lw)
        if y1 < by + bh - photo_margin:
            d.rounded_rectangle([line_x0, y0, x1, y1], radius=max(1, lh // 2), fill=lc)

    # Vermilion dot (bookmark) on spine top
    dot_r = max(2, int(s * 0.028))
    dot_cx = (lx1 + rx0) // 2
    dot_cy = by - dot_r // 2
    d.ellipse([dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r], fill=VERMILION)

    return img


def build_iconset(out_dir: Path) -> None:
    iconset = out_dir / "AppIcon.iconset"
    iconset.mkdir(parents=True, exist_ok=True)

    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for sz in sizes:
        icon = draw_icon(sz)
        icon.save(iconset / f"icon_{sz}x{sz}.png")
        # @2x variants (double the logical size)
        if sz <= 512:
            icon2x = draw_icon(sz * 2)
            icon2x.save(iconset / f"icon_{sz}x{sz}@2x.png")

    print(f"Iconset written to {iconset}")


def save_favicon(out_path: Path) -> None:
    icon = draw_icon(512)
    icon.save(out_path, format="PNG")
    print(f"Favicon written to {out_path}")


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    build_iconset(project_root / "assets")
    save_favicon(project_root / "src/editor/static/favicon.png")
