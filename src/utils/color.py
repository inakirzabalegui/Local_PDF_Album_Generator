"""Color extraction utilities using ColorThief."""

from __future__ import annotations

from pathlib import Path

from colorthief import ColorThief


def dominant_color(image_path: Path) -> tuple[int, int, int]:
    """Extract the single dominant color from an image file."""
    try:
        ct = ColorThief(str(image_path))
        return ct.get_color(quality=5)
    except Exception:
        return (0, 0, 255)


def page_background_color(image_paths: list[Path]) -> tuple[int, int, int]:
    """Compute a weighted-average dominant color for a set of images.

    Falls back to blue (0, 0, 255) if extraction fails for all images.
    """
    if not image_paths:
        return (0, 0, 255)

    r_sum, g_sum, b_sum = 0, 0, 0
    count = 0

    for path in image_paths:
        try:
            r, g, b = dominant_color(path)
            r_sum += r
            g_sum += g
            b_sum += b
            count += 1
        except Exception:
            continue

    if count == 0:
        return (0, 0, 255)

    return (r_sum // count, g_sum // count, b_sum // count)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert (R, G, B) tuple to '#RRGGBB' hex string."""
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert '#RRGGBB' hex string to (R, G, B) tuple."""
    h = hex_str.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_reportlab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """Convert 0-255 RGB to ReportLab's 0.0-1.0 scale."""
    return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
