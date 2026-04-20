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


@dataclass
class ScanResult:
    """Result of scanning a directory, with special folders separated."""

    photos: list[PhotoInfo] = field(default_factory=list)
    cover_photos: list[PhotoInfo] = field(default_factory=list)
    backcover_photos: list[PhotoInfo] = field(default_factory=list)


def scan_directory(source_dir: Path) -> ScanResult:
    """Recursively scan *source_dir* for valid images and extract metadata.

    Special folders "portada" and "contraportada" (case-insensitive) are
    detected and their photos are returned separately. These folders are
    excluded from normal content processing.

    Subdirectories of *source_dir* are treated as source groups; files
    directly inside *source_dir* belong to the group named after the
    directory itself.
    """
    result = ScanResult()

    for path in source_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in VALID_EXTENSIONS:
            continue

        # Determine if this photo belongs to a special folder
        special_type = _detect_special_folder(path, source_dir)
        
        if special_type == "skip":
            continue

        group, sub = _resolve_group(path, source_dir)
        w, h = _read_dimensions(path)

        if w == 0 or h == 0:
            continue

        date = _read_exif_date(path)

        photo = PhotoInfo(
            path=path,
            date_taken=date,
            source_group=group,
            sub_group=sub,
            width=w,
            height=h,
        )

        # Route to appropriate list
        if special_type == "cover":
            result.cover_photos.append(photo)
        elif special_type == "backcover":
            result.backcover_photos.append(photo)
        else:
            result.photos.append(photo)

    return result


def _detect_special_folder(photo_path: Path, root: Path) -> str:
    """Detect if photo is in a special folder (portada/contraportada).
    
    Returns:
        "cover" if in portada folder
        "backcover" if in contraportada folder
        "skip" if in a special folder but should be skipped
        "" if normal photo
    """
    rel = photo_path.relative_to(root)
    
    # Check if any parent folder is a special folder (case-insensitive)
    for part in rel.parts[:-1]:  # Exclude filename itself
        part_lower = part.lower()
        if part_lower == "portada":
            return "cover"
        elif part_lower == "contraportada":
            return "backcover"
    
    return ""


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
