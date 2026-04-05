"""Image downsampling to fit target print resolution."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

TARGET_DPI = 300

A4_CM = (21.0, 29.7)
A4_PIXELS = tuple(int(cm / 2.54 * TARGET_DPI) for cm in A4_CM)


def downsample_image(src: Path, dst: Path, *, dpi: int = TARGET_DPI) -> Path:
    """Copy *src* to *dst*, resizing so it doesn't exceed A4 at *dpi*.

    The aspect ratio is preserved. The image is only shrunk, never enlarged.
    Returns the destination path.
    """
    max_w, max_h = A4_PIXELS

    with Image.open(src) as img:
        img = _apply_exif_rotation(img)
        orig_w, orig_h = img.size

        if orig_w > max_w or orig_h > max_h:
            ratio = min(max_w / orig_w, max_h / orig_h)
            new_size = (int(orig_w * ratio), int(orig_h * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst, format="JPEG", quality=85, dpi=(dpi, dpi))

    return dst


def _apply_exif_rotation(img: Image.Image) -> Image.Image:
    """Auto-rotate image based on EXIF orientation tag."""
    try:
        from PIL import ImageOps
        return ImageOps.exif_transpose(img)  # type: ignore[return-value]
    except Exception:
        return img
