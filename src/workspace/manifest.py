"""Photo manifest: stable mapping between workspace images and source photos.

Each page folder contains a `.photo_manifest.yaml` listing which source photo
each `img_NNN.jpg` came from. This enables non-destructive sync between source
and workspace (light regen) without losing manual page edits.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("album")

MANIFEST_FILENAME = ".photo_manifest.yaml"
SIGNATURE_BYTES = 8192  # bytes hashed for fast signature


@dataclass
class PhotoManifestEntry:
    image_name: str            # e.g. "img_001.jpg"
    source_path: str           # path relative to source root, POSIX-style
    source_mtime: float = 0.0
    sha1: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_mtime": self.source_mtime,
            "sha1": self.sha1,
        }


@dataclass
class PageManifest:
    folder: Path
    section_id: str = ""
    photos: dict[str, PhotoManifestEntry] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "photos": {name: e.to_dict() for name, e in self.photos.items()},
        }


def compute_photo_signature(path: Path) -> tuple[float, str]:
    """Return (mtime, sha1 of first SIGNATURE_BYTES). sha1 empty on error."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return 0.0, ""
    try:
        with open(path, "rb") as f:
            chunk = f.read(SIGNATURE_BYTES)
        sha = hashlib.sha1(chunk).hexdigest()
    except OSError:
        sha = ""
    return mtime, sha


def relative_source_path(source_root: Path, photo_path: Path) -> str:
    """Return POSIX-style path of photo_path relative to source_root.

    Falls back to absolute path string if photo_path is outside source_root.
    """
    try:
        rel = photo_path.resolve().relative_to(source_root.resolve())
        return rel.as_posix()
    except ValueError:
        return photo_path.as_posix()


def read_page_manifest(page_folder: Path) -> PageManifest | None:
    """Read manifest from a page folder. Returns None if missing or unreadable."""
    path = page_folder / MANIFEST_FILENAME
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to read manifest {path}: {e}")
        return None

    photos_raw = data.get("photos", {}) or {}
    photos: dict[str, PhotoManifestEntry] = {}
    for name, entry in photos_raw.items():
        if not isinstance(entry, dict):
            continue
        photos[name] = PhotoManifestEntry(
            image_name=name,
            source_path=str(entry.get("source_path", "")),
            source_mtime=float(entry.get("source_mtime", 0.0)),
            sha1=str(entry.get("sha1", "")),
        )

    return PageManifest(
        folder=page_folder,
        section_id=str(data.get("section_id", "")),
        photos=photos,
    )


def write_page_manifest(manifest: PageManifest) -> Path:
    """Write manifest to <folder>/.photo_manifest.yaml."""
    path = manifest.folder / MANIFEST_FILENAME
    data = manifest.to_dict()
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    return path


def remove_photo_from_manifest(page_folder: Path, image_name: str) -> bool:
    """Drop an entry from a page's manifest. Returns True if removed."""
    manifest = read_page_manifest(page_folder)
    if manifest is None or image_name not in manifest.photos:
        return False
    del manifest.photos[image_name]
    write_page_manifest(manifest)
    return True


def pop_manifest_entry(page_folder: Path, image_name: str) -> PhotoManifestEntry | None:
    """Remove and return a single manifest entry. Returns None if missing."""
    manifest = read_page_manifest(page_folder)
    if manifest is None or image_name not in manifest.photos:
        return None
    entry = manifest.photos.pop(image_name)
    write_page_manifest(manifest)
    return entry


def add_photo_to_manifest(
    page_folder: Path,
    image_name: str,
    source_path: str,
    source_mtime: float = 0.0,
    sha1: str = "",
    section_id: str | None = None,
) -> bool:
    """Upsert a single entry into a page's manifest, creating the file if needed."""
    manifest = read_page_manifest(page_folder)
    if manifest is None:
        manifest = PageManifest(folder=page_folder, section_id=section_id or "")
    elif section_id and not manifest.section_id:
        manifest.section_id = section_id
    manifest.photos[image_name] = PhotoManifestEntry(
        image_name=image_name,
        source_path=source_path,
        source_mtime=source_mtime,
        sha1=sha1,
    )
    write_page_manifest(manifest)
    return True


def move_photo_in_manifest(
    src_folder: Path,
    dst_folder: Path,
    src_image_name: str,
    dst_image_name: str,
    dst_section_id: str | None = None,
) -> bool:
    """Move a manifest entry from src page to dst page, preserving source metadata.

    Returns True if the source entry existed and was relocated.
    """
    entry = pop_manifest_entry(src_folder, src_image_name)
    if entry is None:
        return False
    add_photo_to_manifest(
        dst_folder,
        dst_image_name,
        source_path=entry.source_path,
        source_mtime=entry.source_mtime,
        sha1=entry.sha1,
        section_id=dst_section_id,
    )
    return True


def collect_workspace_manifests(workspace: Path) -> list[PageManifest]:
    """Read all page manifests in a workspace, sorted by page folder name."""
    manifests: list[PageManifest] = []
    for sub in sorted(workspace.iterdir()):
        if not sub.is_dir():
            continue
        m = read_page_manifest(sub)
        if m is not None:
            manifests.append(m)
    return manifests


def workspace_has_manifests(workspace: Path) -> bool:
    """True if at least one page folder contains a manifest."""
    if not workspace.exists():
        return False
    for sub in workspace.iterdir():
        if sub.is_dir() and (sub / MANIFEST_FILENAME).exists():
            return True
    return False
