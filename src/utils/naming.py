"""Naming utilities for folder and section title parsing."""

from __future__ import annotations

import re


def prettify_folder_name(name: str) -> str:
    """Transform a folder name into a friendly display title.
    
    Examples:
        '20260109_Comida_Despedida_Js' -> 'Comida despedida Js'
        'Vacaciones_Verano' -> 'Vacaciones verano'
        '2026' -> '2026'
    """
    cleaned = re.sub(r"^\d{8}_?", "", name)
    cleaned = cleaned.replace("_", " ").strip()
    
    if not cleaned:
        return name.replace("_", " ").strip()
    
    return cleaned[0].upper() + cleaned[1:]


def folder_name_to_slug(name: str) -> str:
    """Convert a display title to a filesystem-safe slug.
    
    Examples:
        'Comida despedida Js' -> 'comida_despedida_js'
        'Vacaciones Verano' -> 'vacaciones_verano'
    """
    return name.lower().replace(" ", "_")


def extract_date_from_folder(name: str) -> str | None:
    """Extract and format date from folder name.
    
    Examples:
        '20260109_Comida_Despedida_Js' -> '09/01/2026'
        'Vacaciones_Verano' -> None
    """
    m = re.match(r"^(\d{4})(\d{2})(\d{2})_?", name)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return None


def build_section_title(folder_name: str) -> str:
    """Build complete section title with date and name.
    
    Examples:
        '20260109_Comida_Despedida_Js' -> '09/01/2026 - Comida despedida Js'
        'Vacaciones_Verano' -> 'Vacaciones verano'
    """
    date = extract_date_from_folder(folder_name)
    pretty = prettify_folder_name(folder_name)
    
    if date:
        return f"{date} - {pretty}"
    return pretty
