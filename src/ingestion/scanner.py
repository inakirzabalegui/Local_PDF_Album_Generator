"""Recursive directory scanner with EXIF metadata extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import exifread
from PIL import Image

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png"}


@dataclass
class PhotoInfo:
    """Metadata for a single discovered photo."""

    path: Path
    date_taken: datetime | None = None
    source_group: str = ""
    sub_group: str = ""
    width: int = 0
    height: int = 0

    @property
    def has_date(self) -> bool:
        return self.date_taken is not None


def scan_directory(source_dir: Path) -> list[PhotoInfo]:
    """Recursively scan *source_dir* for valid images and extract metadata.

    Subdirectories of *source_dir* are treated as source groups; files
    directly inside *source_dir* belong to the group named after the
    directory itself.
    """
    photos: list[PhotoInfo] = []

    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in VALID_EXTENSIONS:
            continue

        group, sub = _resolve_group(path, source_dir)
        w, h = _read_dimensions(path)

        if w == 0 or h == 0:
            continue

        date = _read_exif_date(path)

        photos.append(
            PhotoInfo(
                path=path,
                date_taken=date,
                source_group=group,
                sub_group=sub,
                width=w,
                height=h,
            )
        )

    return photos


def _resolve_group(photo_path: Path, root: Path) -> tuple[str, str]:
    """Determine (source_group, sub_group) from the photo's relative position.

    source_group is the immediate child directory of root.
    sub_group is the grandchild directory (one level deeper), or "" for
    loose photos sitting directly in the source_group folder.
    """
    rel = photo_path.relative_to(root)
    if len(rel.parts) == 1:
        return root.name, ""
    group = rel.parts[0]
    sub = rel.parts[1] if len(rel.parts) >= 3 else ""
    return group, sub


def _read_exif_date(path: Path) -> datetime | None:
    """Try to extract DateTimeOriginal from EXIF data."""
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, stop_tag="DateTimeOriginal", details=False)
        raw = tags.get("EXIF DateTimeOriginal")
        if raw:
            return datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass

    try:
        img = Image.open(path)
        exif = img._getexif()  # type: ignore[attr-defined]
        if exif and 36867 in exif:
            return datetime.strptime(exif[36867], "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass

    return None


def _read_dimensions(path: Path) -> tuple[int, int]:
    """Return (width, height) of an image without fully loading it."""
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return (0, 0)
