"""YAML configuration management for global and per-page state."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

# Path to the default configuration file at repository root
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "global_config_default.yaml"


# ── Templates with comments ──────────────────────────────────────────────────────

GLOBAL_CONFIG_TEMPLATE = """# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL_CONFIG.YAML - Configuración global del álbum
# ═══════════════════════════════════════════════════════════════════════════════
# Este archivo contiene los parámetros globales que afectan a todo el álbum.
# Modifica estos valores según tus preferencias y luego ejecuta --render.

# Tamaño de página (típicamente A4)
page_size: {page_size}

# Resolución objetivo para descarga de imágenes (DPI)
# Valores típicos: 150 (web), 300 (impresión de calidad), 600 (impresión profesional)
target_resolution_dpi: {target_resolution_dpi}

# Número mínimo de fotos por página
# Menor = menos páginas, más fotos/página
photos_per_page_min: {photos_per_page_min}

# Número máximo de fotos por página
# Mayor = más fotos/página, menos espaciadas
photos_per_page_max: {photos_per_page_max}

# Máximo de páginas por volumen PDF antes de dividir en múltiples archivos
# Si el álbum tiene más de N páginas, se generarán Volumen 1, Volumen 2, etc.
# IMPORTANTE: Peecho (impresión) requiere 24-500 páginas por libro.
# Recomendado: máximo 498 (para permitir portada + contraportada)
max_pages_per_volume: {max_pages_per_volume}

# Color de fondo por defecto (formato hex RGB)
# Se usa si ColorThief no puede extraer dominante automático
# Ejemplos: "#FFFFFF" (blanco), "#000000" (negro), "#E8E8E8" (gris claro)
default_background_color: '{default_background_color}'

# Tipografía del sistema para títulos y números de página
# Opciones disponibles: Helvetica, Times-Roman, Courier
typography_system_font: {typography_system_font}

# ─────────────────────────────────────────────────────────────────────────────
# Sistema de pesos para fotos destacadas
# ─────────────────────────────────────────────────────────────────────────────
# Las fotos pueden tener pesos diferentes para ocupar más espacio en la página:
#   - normal (1x): tamaño estándar (no necesita especificar)
#   - destacada (1.5x): 50% más grande
#   - protagonista (2.5x): 2.5x más grande (héroe de la página)
#
# Se especifican en page_config.yaml con 'featured_photos' y 'hero_photos'

# Multiplicador para fotos destacadas (featured_photos)
weight_destacada: {weight_destacada}

# Multiplicador para fotos protagonistas (hero_photos)
weight_protagonista: {weight_protagonista}

# ─────────────────────────────────────────────────────────────────────────────
# Parámetros generados automáticamente (NO editar directamente)
# ─────────────────────────────────────────────────────────────────────────────

# Título del álbum (derivado del nombre de la carpeta origen)
project_title: {project_title}

# Rango de fechas del álbum (calculado automáticamente)
# Formato: DD/MM/YYYY - DD/MM/YYYY
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
# Ejemplos: "#FFFFFF" (blanco), "#FFF8DC" (cornsilk), "#F5F5F5" (gris muy claro)
override_background_color: {override_background_color}

# Marcas de portada/contraportada (NO editar)
is_cover: {is_cover}
is_backcover: {is_backcover}

# ─────────────────────────────────────────────────────────────────────────────
# Títulos de sección
# ─────────────────────────────────────────────────────────────────────────────
# Lista de títulos que aparecen en la página:
#   - Primer título: nombre de la sección (evento/carpeta)
#   - Segundo título (opcional): nombre de subcarpeta si hay fotos de subcarpetas
#
# NO editar - se genera automáticamente
section_titles: {section_titles}

# ─────────────────────────────────────────────────────────────────────────────
# Modo de layout
# ─────────────────────────────────────────────────────────────────────────────
# Define cómo se distribuyen las fotos en la página:
#
# • mesa_de_luz: Rotación suave (+/-3°), jitter de posición, fill factor 93%
#   → Estético, natural, como fotos colocadas sobre una mesa
#
# • grid_compacto: Sin rotación, máxima densidad, fill factor 97%
#   → Limpio, ordenado, máximo aprovechamiento de espacio
#
# • hibrido: Rotación muy sutil (+/-1.5°), compacto, fill factor 95%
#   → Balance entre estético y eficiente
#
layout_mode: {layout_mode}

# ─────────────────────────────────────────────────────────────────────────────
# Sistema de pesos para fotos destacadas
# ─────────────────────────────────────────────────────────────────────────────
# Especifica qué fotos deben ocupar más espacio en la página.
# El nombre debe coincidir EXACTAMENTE con el nombre del archivo.
#
# TRES NIVELES DE ÉNFASIS:
#
# 1. featured_photos (1.5x tamaño normal)
#    └─ Para fotos importantes pero no las principales
#    └─ Ejemplo: primer plano grupal, atardecer bonito
#
# 2. hero_photos (2.5x tamaño normal)
#    └─ Para la foto estrella de la página
#    └─ Ejemplo: foto principal del evento, momento único
#    └─ Solo recomendado 1-2 por página
#
# CÓMO FUNCIONA:
#   El algoritmo de layout trata las fotos pesadas como si ocuparan múltiples
#   "slots". Esto hace que ocupen naturalmente más espacio sin romper el diseño.
#
# EJEMPLOS:
#
# featured_photos:
#   - IMG_042.jpg      # Foto importante, 1.5x más grande
#   - IMG_087.jpg      # Otra foto importante, 1.5x más grande
#
# hero_photos:
#   - IMG_001.jpg      # Foto principal, 2.5x más grande (la estrella)
#
# IMPORTANTE:
#   • Los nombres deben coincidir con los archivos en esta carpeta
#   • NO incluyas la misma foto en ambas listas (hero toma precedencia)
#   • Una foto no puede estar en featured_photos si está en hero_photos
#   • Deja vacío si no quieres fotos destacadas
#
featured_photos: {featured_photos}
hero_photos: {hero_photos}
"""

# ── Data models ──────────────────────────────────────────────────────────────


def _load_default_config() -> dict[str, Any]:
    """Load default configuration from global_config_default.yaml.
    
    Returns empty dict if file doesn't exist (use hardcoded defaults).
    """
    if DEFAULT_CONFIG_PATH.exists():
        try:
            with open(DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return data
        except Exception:
            pass
    return {}


_DEFAULT_CONFIG = _load_default_config()


@dataclass
class GlobalConfig:
    page_size: str = _DEFAULT_CONFIG.get("page_size", "A4")
    target_resolution_dpi: int = _DEFAULT_CONFIG.get("target_resolution_dpi", 300)
    photos_per_page_min: int = _DEFAULT_CONFIG.get("photos_per_page_min", 6)
    photos_per_page_max: int = _DEFAULT_CONFIG.get("photos_per_page_max", 10)
    max_pages_per_volume: int = _DEFAULT_CONFIG.get("max_pages_per_volume", 100)
    default_background_color: str = _DEFAULT_CONFIG.get("default_background_color", "#0000FF")
    typography_system_font: str = _DEFAULT_CONFIG.get("typography_system_font", "Helvetica")
    weight_destacada: float = _DEFAULT_CONFIG.get("weight_destacada", 1.5)
    weight_protagonista: float = _DEFAULT_CONFIG.get("weight_protagonista", 2.5)
    project_title: str = "Album"
    date_range: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_size": self.page_size,
            "target_resolution_dpi": self.target_resolution_dpi,
            "photos_per_page_min": self.photos_per_page_min,
            "photos_per_page_max": self.photos_per_page_max,
            "max_pages_per_volume": self.max_pages_per_volume,
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

    def get_photo_weight(self, filename: str, global_cfg: GlobalConfig) -> float:
        """Return the weight multiplier for a given photo filename.
        
        Returns:
            - weight_protagonista if photo is in hero_photos
            - weight_destacada if photo is in featured_photos
            - 1.0 for normal photos
        """
        if filename in self.hero_photos:
            return global_cfg.weight_protagonista
        elif filename in self.featured_photos:
            return global_cfg.weight_destacada
        return 1.0


# ── Writers ──────────────────────────────────────────────────────────────────


def write_global_config(workspace: Path, cfg: GlobalConfig) -> Path:
    path = workspace / "global_config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Format the color as a YAML string (with quotes)
    color_str = f'"{cfg.default_background_color}"'
    
    # Format project_title with quotes if it's numeric to prevent YAML parsing as int
    title_str = cfg.project_title
    if title_str.isdigit():
        title_str = f'"{title_str}"'
    
    content = GLOBAL_CONFIG_TEMPLATE.format(
        page_size=cfg.page_size,
        target_resolution_dpi=cfg.target_resolution_dpi,
        photos_per_page_min=cfg.photos_per_page_min,
        photos_per_page_max=cfg.photos_per_page_max,
        max_pages_per_volume=cfg.max_pages_per_volume,
        default_background_color=cfg.default_background_color,
        typography_system_font=cfg.typography_system_font,
        weight_destacada=cfg.weight_destacada,
        weight_protagonista=cfg.weight_protagonista,
        project_title=title_str,
        date_range=cfg.date_range,
    )
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    
    return path


def write_page_configs(page_map: list[PageConfig]) -> None:
    for pc in page_map:
        path = pc.folder / "page_config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Format lists as YAML - empty lists as empty, non-empty as YAML list syntax
        featured_str = "[]" if not pc.featured_photos else "\n  - " + "\n  - ".join(pc.featured_photos)
        hero_str = "[]" if not pc.hero_photos else "\n  - " + "\n  - ".join(pc.hero_photos)
        
        # Format optional color
        color_str = "null" if pc.override_background_color is None else f'"{pc.override_background_color}"'
        
        # Format section titles
        if not pc.section_titles:
            titles_str = "[]"
        else:
            titles_str = "\n  - " + "\n  - ".join(f'"{t}"' for t in pc.section_titles)
        
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
        )
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


# ── Readers ──────────────────────────────────────────────────────────────────


def read_global_config(workspace: Path) -> GlobalConfig:
    path = workspace / "global_config.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    
    # Ensure project_title is always a string (YAML may parse numeric titles as int)
    if "project_title" in data and not isinstance(data["project_title"], str):
        data["project_title"] = str(data["project_title"])
    
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
                section_titles=data.get("section_titles", []),
                layout_mode=data.get("layout_mode", "mesa_de_luz"),
                featured_photos=data.get("featured_photos", []),
                hero_photos=data.get("hero_photos", []),
            )
        )

    pages.sort(key=lambda p: p.page_number)
    return pages
