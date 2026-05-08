"""Data-driven provider registry.

Loads YAML definitions from `src/printing/data/` and exposes a single
`DataDrivenProvider` class implementing the `Provider` protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src.printing.provider import (
    CoverSpec,
    PageSpec,
    ProductDescriptor,
    Provider,
)

_DATA_DIR = Path(__file__).parent / "data"


@dataclass
class DataDrivenProvider:
    """Provider implementation backed by a single YAML file."""

    name: str
    label: str
    _data: dict[str, Any]

    def list_products(self) -> list[ProductDescriptor]:
        out: list[ProductDescriptor] = []
        for pid, pdata in self._data.get("products", {}).items():
            variants = list(pdata.get("paper_variants", {}).keys())
            default_variant = pdata.get("default_paper_variant", variants[0] if variants else "standard")
            out.append(ProductDescriptor(
                id=pid,
                label=pdata.get("label", pid),
                paper_variants=variants,
                default_paper_variant=default_variant,
            ))
        return out

    def _product_block(self, product: str) -> dict[str, Any]:
        products = self._data.get("products", {})
        if product not in products:
            raise KeyError(f"Provider '{self.name}' has no product '{product}'")
        return products[product]

    def _variant_block(self, product: str, paper_variant: str) -> dict[str, Any]:
        product_block = self._product_block(product)
        variants = product_block.get("paper_variants", {})
        if paper_variant not in variants:
            raise KeyError(
                f"Provider '{self.name}' product '{product}' has no paper_variant '{paper_variant}'"
            )
        return variants[paper_variant]

    def page_spec(self, product: str, paper_variant: str = "standard") -> PageSpec:
        pblock = self._product_block(product)
        page = pblock["page"]
        bleed = page["bleed"]
        insets = page["safe_insets"]

        variant = self._variant_block(product, paper_variant)
        max_pages = variant.get("max_pages", pblock.get("max_pages", 500))
        min_pages = variant.get("min_pages", pblock.get("min_pages"))

        return PageSpec(
            trim_w_cm=float(page["trim_w_cm"]),
            trim_h_cm=float(page["trim_h_cm"]),
            bleed_top_cm=float(bleed["top_cm"]),
            bleed_bottom_cm=float(bleed["bottom_cm"]),
            bleed_outside_cm=float(bleed["outside_cm"]),
            bleed_inside_cm=float(bleed["inside_cm"]),
            safe_inset_outside_cm=float(insets["outside_cm"]),
            safe_inset_binding_cm=float(insets["binding_cm"]),
            safe_inset_top_cm=float(insets.get("top_cm", insets["outside_cm"])),
            safe_inset_bottom_cm=float(insets.get("bottom_cm", insets["outside_cm"])),
            max_pages=int(max_pages),
            min_pages=int(min_pages) if min_pages is not None else None,
        )

    def cover_spec(self, product: str, paper_variant: str, page_count: int) -> CoverSpec:
        pblock = self._product_block(product)
        cover = pblock["cover"]
        variant = self._variant_block(product, paper_variant)

        # Auto-compute spine: caliper × pages + offset (linear).
        spine = (
            float(variant.get("spine_caliper_cm_per_page", 0.0)) * page_count
            + float(variant.get("spine_offset_cm", 0.0))
        )
        spine = max(0.0, spine)

        cover_trim_w = float(variant.get("cover_trim_w_cm", pblock["page"]["trim_w_cm"]))
        page_trim_w = float(pblock["page"]["trim_w_cm"])
        hinge = float(cover.get("hinge_w_cm", 0.0))

        # Derive flap width so the layout fills cover_trim_w exactly:
        # cover_trim_w = 2*flap + 2*hinge + 2*page_trim_w + spine
        if cover.get("mode", "wraparound") == "wraparound":
            flap = max(0.0, (cover_trim_w - 2 * page_trim_w - 2 * hinge - spine) / 2.0)
        else:
            flap = 0.0

        return CoverSpec(
            trim_w_cm=cover_trim_w,
            trim_h_cm=float(cover.get("trim_h_cm", pblock["page"]["trim_h_cm"])),
            bleed_cm=float(cover.get("bleed_cm", 0.0)),
            flap_w_cm=flap,
            spine_w_cm=spine,
            hinge_w_cm=hinge,
            safe_inset_cm=float(cover.get("safe_inset_cm", 0.635)),
            mode=cover.get("mode", "wraparound"),
        )

    def validate_page_count(self, product: str, paper_variant: str, page_count: int) -> list[str]:
        warnings: list[str] = []
        spec = self.page_spec(product, paper_variant)
        if spec.min_pages is not None and page_count < spec.min_pages:
            warnings.append(
                f"{self.label}: el producto requiere al menos {spec.min_pages} páginas "
                f"(actuales: {page_count})."
            )
        if page_count > spec.max_pages:
            warnings.append(
                f"{self.label}: el producto admite como máximo {spec.max_pages} páginas "
                f"(actuales: {page_count})."
            )
        if page_count % 2 != 0:
            warnings.append(f"{self.label}: el número de páginas debe ser par (actuales: {page_count}).")
        return warnings

    def supports_embedded_cover(self, product: str) -> bool:
        cover = self._product_block(product).get("cover", {})
        return cover.get("mode", "wraparound") == "embedded"


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=None)
def _load_provider_data(name: str) -> DataDrivenProvider:
    path = _DATA_DIR / f"{name}.yaml"
    if not path.exists():
        raise KeyError(f"Provider '{name}' not found (expected {path}).")
    data = _load_yaml(path)
    return DataDrivenProvider(
        name=data.get("name", name),
        label=data.get("label", name.capitalize()),
        _data=data,
    )


def load_provider(name: str) -> Provider:
    """Return the Provider implementation for a given name (case-insensitive)."""
    return _load_provider_data(name.lower())


def list_providers() -> list[tuple[str, str]]:
    """Return [(name, label), ...] for every YAML present in data/."""
    out: list[tuple[str, str]] = []
    for path in sorted(_DATA_DIR.glob("*.yaml")):
        try:
            data = _load_yaml(path)
        except Exception:
            continue
        out.append((data.get("name", path.stem), data.get("label", path.stem.capitalize())))
    return out
