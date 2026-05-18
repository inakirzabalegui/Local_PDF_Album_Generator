"""YAML configuration management for global and per-page state."""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.printing.overrides import resolve_specs
from src.workspace.atomic_yaml import write_text as _atomic_write_text
from src.printing.provider import (
    CoverSpec,
    OverridesConfig,
    PageSpec,
    ProviderConfig,
)
from src.printing.registry import load_provider

logger = logging.getLogger("album")

VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "global_config_default.yaml"


# ── Templates with comments ──────────────────────────────────────────────────────

GLOBAL_CONFIG_TEMPLATE = """# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL_CONFIG.YAML - Configuración global del álbum
# ═══════════════════════════════════════════════════════════════════════════════
# Configuración del álbum: proveedor de impresión, dimensiones y parámetros
# de composición. Modifica y vuelve a ejecutar --render para aplicar cambios.

# ─────────────────────────────────────────────────────────────────────────────
# Proveedor de impresión
# ─────────────────────────────────────────────────────────────────────────────
# Selecciona el proveedor, producto y tipo de papel. Los archivos de
# definición viven en src/printing/data/<provider>.yaml.
#
# Proveedores disponibles:
#   blurb   – Blurb.com (recomendado)
#   peecho  – Peecho legacy (A4)
#   custom  – Medidas 100% manuales (vía overrides)
provider:
  name: {provider_name}
  product: {provider_product}
  paper_variant: {provider_paper_variant}

# ─────────────────────────────────────────────────────────────────────────────
# Overrides opcionales
# ─────────────────────────────────────────────────────────────────────────────
# Cualquier campo a 'null' usa el valor del proveedor. Especificar un número
# (en cm) sobrescribe el valor automático.
overrides:
  page:
    trim_w_cm: {ov_page_trim_w_cm}
    trim_h_cm: {ov_page_trim_h_cm}
    bleed_top_cm: {ov_page_bleed_top_cm}
    bleed_bottom_cm: {ov_page_bleed_bottom_cm}
    bleed_outside_cm: {ov_page_bleed_outside_cm}
    bleed_inside_cm: {ov_page_bleed_inside_cm}
    safe_inset_outside_cm: {ov_page_safe_inset_outside_cm}
    safe_inset_binding_cm: {ov_page_safe_inset_binding_cm}
    safe_inset_top_cm: {ov_page_safe_inset_top_cm}
    safe_inset_bottom_cm: {ov_page_safe_inset_bottom_cm}
  cover:
    trim_w_cm: {ov_cover_trim_w_cm}
    trim_h_cm: {ov_cover_trim_h_cm}
    bleed_cm: {ov_cover_bleed_cm}
    flap_w_cm: {ov_cover_flap_w_cm}
    spine_w_cm: {ov_cover_spine_w_cm}      # null = autocálculo por nº páginas
    hinge_w_cm: {ov_cover_hinge_w_cm}
    safe_inset_cm: {ov_cover_safe_inset_cm}
  rendering:
    binding_side_for_odd: {ov_binding_side_for_odd}
    max_pages_per_volume: {ov_max_pages_per_volume}

# ─────────────────────────────────────────────────────────────────────────────
# Imágenes y composición
# ─────────────────────────────────────────────────────────────────────────────
# Resolución objetivo para descarga de imágenes (DPI)
target_resolution_dpi: {target_resolution_dpi}

# Número mínimo y máximo de fotos por página
photos_per_page_min: {photos_per_page_min}
photos_per_page_max: {photos_per_page_max}

# Color de fondo por defecto (formato hex RGB) cuando no se puede extraer
default_background_color: '{default_background_color}'

# Tipografía del sistema (Helvetica, Times-Roman, Courier, ...)
typography_system_font: {typography_system_font}

# Multiplicadores de peso para fotos destacadas/protagonistas
weight_destacada: {weight_destacada}
weight_protagonista: {weight_protagonista}

# ─────────────────────────────────────────────────────────────────────────────
# Parámetros generados automáticamente (NO editar)
# ─────────────────────────────────────────────────────────────────────────────
project_title: {project_title}
date_range: '{date_range}'
"""

PAGE_CONFIG_TEMPLATE = """# ═══════════════════════════════════════════════════════════════════════════════
# PAGE_CONFIG.YAML - Configuración de página
# ═══════════════════════════════════════════════════════════════════════════════
# Este archivo contiene los parámetros específicos de esta página.
# Puedes editarlo antes de ejecutar --render para personalizar la composición.

# Número de página (NO editar - se regenera automáticamente)
page_number: {page_number}

# Número de fotos en esta página (información, NO editar)
photo_count: {photo_count}

# Seed para generación reproducible del layout aleatorio
# NO editar a menos que quieras cambiar completamente la composición
layout_seed: {layout_seed}

# Color de fondo personalizado para esta página (opcional)
# Deja como 'null' para usar el color calculado automáticamente
# Formato hex: "#RRGGBB"
override_background_color: {override_background_color}

# Marcas de portada/contraportada (NO editar)
is_cover: {is_cover}
is_backcover: {is_backcover}

# ─────────────────────────────────────────────────────────────────────────────
# Títulos de sección
# ─────────────────────────────────────────────────────────────────────────────
section_titles: {section_titles}

# ─────────────────────────────────────────────────────────────────────────────
# Modo de layout (mesa_de_luz | grid_compacto | hibrido)
# ─────────────────────────────────────────────────────────────────────────────
layout_mode: {layout_mode}

# ─────────────────────────────────────────────────────────────────────────────
# Sistema de pesos para fotos destacadas
# ─────────────────────────────────────────────────────────────────────────────
featured_photos: {featured_photos}
hero_photos: {hero_photos}

# ─────────────────────────────────────────────────────────────────────────────
# Subtítulos de fotos (captions)
# ─────────────────────────────────────────────────────────────────────────────
photo_captions: {photo_captions}

# Estado de revisión manual
completed: {completed}

# ID estable de sección (NO editar — usado por sync para detectar renames)
section_id: {section_id}

# IDs de sub-grupos (subcarpetas del evento) cuyas fotos aparecen en esta página.
# El syncer reconstruye section_titles[1] a partir de estos IDs en cada sync.
# (NO editar — gestionado por el pipeline)
sub_group_ids: {sub_group_ids}

# Fecha de sección en formato DD/MM/YYYY (derivada del prefijo YYYYMMDD_ de la carpeta fuente).
# Usada para reordenar secciones con --resort-sections. Vacío si no hay prefijo de fecha.
section_date: '{section_date}'

# Override manual del subtítulo (section_titles[1]). Si tiene valor, el sync
# respeta este texto literal y NO lo reconstruye desde sub_group_ids.
# null = comportamiento por defecto (derivado del FS).
section_subtitle_override: {section_subtitle_override}
"""

# ── Data models ──────────────────────────────────────────────────────────────


def _load_default_config() -> dict[str, Any]:
    if DEFAULT_CONFIG_PATH.exists():
        try:
            with open(DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}


_DEFAULT_CONFIG = _load_default_config()


def _default_provider_config() -> ProviderConfig:
    raw = _DEFAULT_CONFIG.get("provider", {})
    return ProviderConfig.from_dict(raw)


def _default_overrides() -> OverridesConfig:
    raw = _DEFAULT_CONFIG.get("overrides", {})
    return OverridesConfig.from_dict(raw)


@dataclass
class GlobalConfig:
    provider: ProviderConfig = field(default_factory=_default_provider_config)
    overrides: OverridesConfig = field(default_factory=_default_overrides)
    target_resolution_dpi: int = _DEFAULT_CONFIG.get("target_resolution_dpi", 300)
    photos_per_page_min: int = _DEFAULT_CONFIG.get("photos_per_page_min", 6)
    photos_per_page_max: int = _DEFAULT_CONFIG.get("photos_per_page_max", 10)
    default_background_color: str = _DEFAULT_CONFIG.get("default_background_color", "#0000FF")
    typography_system_font: str = _DEFAULT_CONFIG.get("typography_system_font", "Helvetica")
    weight_destacada: float = _DEFAULT_CONFIG.get("weight_destacada", 1.5)
    weight_protagonista: float = _DEFAULT_CONFIG.get("weight_protagonista", 2.5)
    project_title: str = "Album"
    date_range: str = ""

    # ── Spec resolution ────────────────────────────────────────────────────

    @property
    def page_spec(self) -> PageSpec:
        page, _ = resolve_specs(
            self.provider.name,
            self.provider.product,
            self.provider.paper_variant,
            page_count=0,
            overrides=self.overrides,
        )
        return page

    def cover_spec(self, page_count: int) -> CoverSpec:
        _, cover = resolve_specs(
            self.provider.name,
            self.provider.product,
            self.provider.paper_variant,
            page_count=page_count,
            overrides=self.overrides,
        )
        return cover

    @property
    def max_pages_per_volume(self) -> int:
        ov = self.overrides.rendering.max_pages_per_volume
        if ov is not None:
            return int(ov)
        return self.page_spec.max_pages

    def supports_embedded_cover(self) -> bool:
        provider = load_provider(self.provider.name)
        return provider.supports_embedded_cover(self.provider.product)

    # ── Serialization ──────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider.to_dict(),
            "overrides": self.overrides.to_dict(),
            "target_resolution_dpi": self.target_resolution_dpi,
            "photos_per_page_min": self.photos_per_page_min,
            "photos_per_page_max": self.photos_per_page_max,
            "default_background_color": self.default_background_color,
            "typography_system_font": self.typography_system_font,
            "weight_destacada": self.weight_destacada,
            "weight_protagonista": self.weight_protagonista,
            "project_title": self.project_title,
            "date_range": self.date_range,
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
    section_titles: list[str] = field(default_factory=list)
    layout_mode: str = "mesa_de_luz"
    featured_photos: list[str] = field(default_factory=list)
    hero_photos: list[str] = field(default_factory=list)
    photo_captions: dict[str, str] = field(default_factory=dict)
    completed: bool = False
    section_id: str = ""
    sub_group_ids: list[str] = field(default_factory=list)
    section_date: str = ""
    section_subtitle_override: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "photo_count": self.photo_count,
            "layout_seed": self.layout_seed,
            "override_background_color": self.override_background_color,
            "is_cover": self.is_cover,
            "is_backcover": self.is_backcover,
            "section_titles": self.section_titles,
            "layout_mode": self.layout_mode,
            "featured_photos": self.featured_photos,
            "hero_photos": self.hero_photos,
            "photo_captions": self.photo_captions,
            "completed": self.completed,
            "section_id": self.section_id,
            "sub_group_ids": list(self.sub_group_ids),
            "section_date": self.section_date,
            "section_subtitle_override": self.section_subtitle_override,
        }

    def image_files(self) -> list[Path]:
        if not self.folder.is_dir():
            return []
        return sorted(
            p
            for p in self.folder.iterdir()
            if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
        )

    def get_photo_weight(self, filename: str, global_cfg: GlobalConfig) -> float:
        if filename in self.hero_photos:
            return global_cfg.weight_protagonista
        elif filename in self.featured_photos:
            return global_cfg.weight_destacada
        return 1.0


# ── Writers ──────────────────────────────────────────────────────────────────


def _yaml_null(v: Any) -> str:
    return "null" if v is None else str(v)


def write_global_config(workspace: Path, cfg: GlobalConfig) -> Path:
    path = workspace / "global_config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)

    title_str = cfg.project_title
    if title_str.isdigit():
        title_str = f'"{title_str}"'

    page_ov = cfg.overrides.page
    cov_ov = cfg.overrides.cover
    ren_ov = cfg.overrides.rendering

    content = GLOBAL_CONFIG_TEMPLATE.format(
        provider_name=cfg.provider.name,
        provider_product=cfg.provider.product,
        provider_paper_variant=cfg.provider.paper_variant,
        ov_page_trim_w_cm=_yaml_null(page_ov.trim_w_cm),
        ov_page_trim_h_cm=_yaml_null(page_ov.trim_h_cm),
        ov_page_bleed_top_cm=_yaml_null(page_ov.bleed_top_cm),
        ov_page_bleed_bottom_cm=_yaml_null(page_ov.bleed_bottom_cm),
        ov_page_bleed_outside_cm=_yaml_null(page_ov.bleed_outside_cm),
        ov_page_bleed_inside_cm=_yaml_null(page_ov.bleed_inside_cm),
        ov_page_safe_inset_outside_cm=_yaml_null(page_ov.safe_inset_outside_cm),
        ov_page_safe_inset_binding_cm=_yaml_null(page_ov.safe_inset_binding_cm),
        ov_page_safe_inset_top_cm=_yaml_null(page_ov.safe_inset_top_cm),
        ov_page_safe_inset_bottom_cm=_yaml_null(page_ov.safe_inset_bottom_cm),
        ov_cover_trim_w_cm=_yaml_null(cov_ov.trim_w_cm),
        ov_cover_trim_h_cm=_yaml_null(cov_ov.trim_h_cm),
        ov_cover_bleed_cm=_yaml_null(cov_ov.bleed_cm),
        ov_cover_flap_w_cm=_yaml_null(cov_ov.flap_w_cm),
        ov_cover_spine_w_cm=_yaml_null(cov_ov.spine_w_cm),
        ov_cover_hinge_w_cm=_yaml_null(cov_ov.hinge_w_cm),
        ov_cover_safe_inset_cm=_yaml_null(cov_ov.safe_inset_cm),
        ov_binding_side_for_odd=ren_ov.binding_side_for_odd,
        ov_max_pages_per_volume=_yaml_null(ren_ov.max_pages_per_volume),
        target_resolution_dpi=cfg.target_resolution_dpi,
        photos_per_page_min=cfg.photos_per_page_min,
        photos_per_page_max=cfg.photos_per_page_max,
        default_background_color=cfg.default_background_color,
        typography_system_font=cfg.typography_system_font,
        weight_destacada=cfg.weight_destacada,
        weight_protagonista=cfg.weight_protagonista,
        project_title=title_str,
        date_range=cfg.date_range,
    )

    _atomic_write_text(path, content)

    return path


def write_page_configs(page_map: list[PageConfig]) -> None:
    for pc in page_map:
        path = pc.folder / "page_config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)

        featured_str = "[]" if not pc.featured_photos else "\n  - " + "\n  - ".join(pc.featured_photos)
        hero_str = "[]" if not pc.hero_photos else "\n  - " + "\n  - ".join(pc.hero_photos)

        color_str = "null" if pc.override_background_color is None else f'"{pc.override_background_color}"'

        if not pc.section_titles:
            titles_str = "[]"
        else:
            titles_str = "\n  - " + "\n  - ".join(f'"{t}"' for t in pc.section_titles)

        if not pc.photo_captions:
            captions_str = "{}"
        else:
            captions_str = "\n" + "\n".join(
                f'  {k}: "{v}"' for k, v in pc.photo_captions.items()
            )

        section_id_str = f'"{pc.section_id}"' if pc.section_id else '""'

        if not pc.sub_group_ids:
            sub_group_ids_str = "[]"
        else:
            sub_group_ids_str = "\n  - " + "\n  - ".join(f'"{s}"' for s in pc.sub_group_ids)

        if pc.section_subtitle_override is None:
            subtitle_override_str = "null"
        else:
            escaped = pc.section_subtitle_override.replace('"', '\\"')
            subtitle_override_str = f'"{escaped}"'

        content = PAGE_CONFIG_TEMPLATE.format(
            page_number=pc.page_number,
            photo_count=pc.photo_count,
            layout_seed=pc.layout_seed,
            override_background_color=color_str,
            is_cover=str(pc.is_cover).lower(),
            is_backcover=str(pc.is_backcover).lower(),
            section_titles=titles_str,
            layout_mode=pc.layout_mode,
            featured_photos=featured_str,
            hero_photos=hero_str,
            photo_captions=captions_str,
            completed=str(pc.completed).lower(),
            section_id=section_id_str,
            sub_group_ids=sub_group_ids_str,
            section_date=pc.section_date or "",
            section_subtitle_override=subtitle_override_str,
        )

        _atomic_write_text(path, content)


# ── Readers ──────────────────────────────────────────────────────────────────


def _parse_page_number(folder_name: str) -> int:
    match = re.match(r'pagina_(\d+)', folder_name)
    return int(match.group(1)) if match else 0


def _inherit_from_nearest(existing_pages: list[PageConfig], folder_name: str) -> tuple[list[str], str]:
    match = re.match(r'pagina_\d+_(.*)', folder_name)
    slug = match.group(1) if match else ""

    if slug and existing_pages:
        for page in existing_pages:
            if page.folder.name.endswith(f"_{slug}") or slug in page.folder.name:
                return list(page.section_titles), page.layout_mode

    if existing_pages:
        last = existing_pages[-1]
        return list(last.section_titles), last.layout_mode

    return [], "mesa_de_luz"


def _migrate_legacy_global(data: dict[str, Any]) -> dict[str, Any]:
    """Translate pre-modular schema (page_size: "A4" + max_pages_per_volume) to new shape."""
    if "provider" in data:
        return data  # already new format

    legacy_size = data.get("page_size")
    legacy_max = data.get("max_pages_per_volume")

    if legacy_size is None and legacy_max is None:
        return data  # nothing to migrate

    logger.warning(
        "Detectado global_config.yaml con esquema antiguo. Mapeando provider=peecho/a4 "
        "para preservar el comportamiento. Considera migrar a Blurb manualmente."
    )

    out = dict(data)
    out["provider"] = {"name": "peecho", "product": "a4", "paper_variant": "standard"}
    if legacy_max is not None:
        out.setdefault("overrides", {}).setdefault("rendering", {})["max_pages_per_volume"] = legacy_max
    out.pop("page_size", None)
    out.pop("max_pages_per_volume", None)
    return out


def read_global_config(workspace: Path) -> GlobalConfig:
    path = workspace / "global_config.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    data = _migrate_legacy_global(data)

    if "project_title" in data and not isinstance(data["project_title"], str):
        data["project_title"] = str(data["project_title"])

    cfg = GlobalConfig()
    if "provider" in data:
        cfg.provider = ProviderConfig.from_dict(data["provider"])
    if "overrides" in data:
        cfg.overrides = OverridesConfig.from_dict(data["overrides"])

    for fname in (
        "target_resolution_dpi",
        "photos_per_page_min",
        "photos_per_page_max",
        "default_background_color",
        "typography_system_font",
        "weight_destacada",
        "weight_protagonista",
        "project_title",
        "date_range",
    ):
        if fname in data:
            setattr(cfg, fname, data[fname])

    return cfg


def read_page_configs(workspace: Path, global_cfg: GlobalConfig) -> list[PageConfig]:
    pages: list[PageConfig] = []

    for sub in sorted(workspace.iterdir()):
        if not sub.is_dir():
            continue
        cfg_file = sub / "page_config.yaml"
        if not cfg_file.exists():
            actual_images = sorted(
                p for p in sub.iterdir()
                if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
            )
            if not actual_images:
                continue

            page_num = _parse_page_number(sub.name)
            section_titles, layout_mode = _inherit_from_nearest(pages, sub.name)

            pages.append(PageConfig(
                folder=sub,
                page_number=page_num,
                photo_count=len(actual_images),
                section_titles=section_titles,
                layout_mode=layout_mode,
            ))
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
                section_titles=data.get("section_titles", []),
                layout_mode=data.get("layout_mode", "mesa_de_luz"),
                featured_photos=data.get("featured_photos", []),
                hero_photos=data.get("hero_photos", []),
                photo_captions=data.get("photo_captions", {}),
                completed=data.get("completed", False),
                section_id=data.get("section_id", "") or "",
                sub_group_ids=list(data.get("sub_group_ids", []) or []),
                section_date=str(data.get("section_date", "") or ""),
                section_subtitle_override=(data.get("section_subtitle_override") if data.get("section_subtitle_override") not in (None, "null", "") else None),
            )
        )

    pages.sort(key=lambda p: p.page_number)
    return pages
