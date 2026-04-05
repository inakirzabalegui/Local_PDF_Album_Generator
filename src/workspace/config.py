"""YAML configuration management for global and per-page state."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


# ── Data models ──────────────────────────────────────────────────────────────


@dataclass
class GlobalConfig:
    page_size: str = "A4"
    target_resolution_dpi: int = 300
    photos_per_page_min: int = 4
    photos_per_page_max: int = 9
    max_pages_per_volume: int = 100
    default_background_color: str = "#0000FF"
    typography_system_font: str = "Helvetica"
    project_title: str = "Album"

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_size": self.page_size,
            "target_resolution_dpi": self.target_resolution_dpi,
            "photos_per_page_min": self.photos_per_page_min,
            "photos_per_page_max": self.photos_per_page_max,
            "max_pages_per_volume": self.max_pages_per_volume,
            "default_background_color": self.default_background_color,
            "typography_system_font": self.typography_system_font,
            "project_title": self.project_title,
        }


@dataclass
class PageConfig:
    folder: Path
    page_number: int
    photo_count: int
    layout_seed: int = field(default_factory=lambda: random.randint(0, 2**31))
    override_background_color: str | None = None
    is_cover: bool = False
    is_backcover: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "photo_count": self.photo_count,
            "layout_seed": self.layout_seed,
            "override_background_color": self.override_background_color,
            "is_cover": self.is_cover,
            "is_backcover": self.is_backcover,
        }

    def image_files(self) -> list[Path]:
        """Return sorted list of actual image files in this page folder."""
        if not self.folder.is_dir():
            return []
        return sorted(
            p
            for p in self.folder.iterdir()
            if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
        )


# ── Writers ──────────────────────────────────────────────────────────────────


def write_global_config(workspace: Path, cfg: GlobalConfig) -> Path:
    path = workspace / "global_config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(cfg.to_dict(), f, default_flow_style=False, allow_unicode=True)
    return path


def write_page_configs(page_map: list[PageConfig]) -> None:
    for pc in page_map:
        path = pc.folder / "page_config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(pc.to_dict(), f, default_flow_style=False, allow_unicode=True)


# ── Readers ──────────────────────────────────────────────────────────────────


def read_global_config(workspace: Path) -> GlobalConfig:
    path = workspace / "global_config.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return GlobalConfig(**{k: v for k, v in data.items() if k in GlobalConfig.__dataclass_fields__})


def read_page_configs(workspace: Path, global_cfg: GlobalConfig) -> list[PageConfig]:
    """Read all page_config.yaml files from the workspace, sorted by page number."""
    pages: list[PageConfig] = []

    for sub in sorted(workspace.iterdir()):
        if not sub.is_dir():
            continue
        cfg_file = sub / "page_config.yaml"
        if not cfg_file.exists():
            continue

        with open(cfg_file, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        actual_images = sorted(
            p
            for p in sub.iterdir()
            if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
        )

        pages.append(
            PageConfig(
                folder=sub,
                page_number=data.get("page_number", 0),
                photo_count=len(actual_images),
                layout_seed=data.get("layout_seed", random.randint(0, 2**31)),
                override_background_color=data.get("override_background_color"),
                is_cover=data.get("is_cover", False),
                is_backcover=data.get("is_backcover", False),
            )
        )

    pages.sort(key=lambda p: p.page_number)
    return pages
