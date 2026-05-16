"""Provider data models and protocol.

A *provider* is a print service (Blurb, Peecho, ...). Each provider exposes
one or more *products* (book formats); each product may have multiple *paper
variants* that affect spine thickness on the cover.

Specifications are kept in centimetres throughout; conversion to ReportLab
points happens at consumer sites (1 cm = 28.3464567 pt).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


CM_TO_PT = 28.3464566929  # exact: 72 / 2.54


@dataclass(frozen=True)
class PageSpec:
    """Specification for an interior page."""

    trim_w_cm: float
    trim_h_cm: float
    bleed_top_cm: float
    bleed_bottom_cm: float
    bleed_outside_cm: float
    bleed_inside_cm: float
    safe_inset_outside_cm: float
    safe_inset_binding_cm: float
    safe_inset_top_cm: float
    safe_inset_bottom_cm: float
    max_pages: int
    min_pages: Optional[int] = None

    def trim_w_pt(self) -> float:
        return self.trim_w_cm * CM_TO_PT

    def trim_h_pt(self) -> float:
        return self.trim_h_cm * CM_TO_PT

    def pdf_w_pt(self) -> float:
        """PDF page width in points (trim + outside bleed; inside bleed is 0)."""
        return (self.trim_w_cm + self.bleed_outside_cm + self.bleed_inside_cm) * CM_TO_PT

    def pdf_h_pt(self) -> float:
        return (self.trim_h_cm + self.bleed_top_cm + self.bleed_bottom_cm) * CM_TO_PT


@dataclass(frozen=True)
class CoverSpec:
    """Specification for a wraparound cover (single PDF spanning back+spine+front)."""

    trim_w_cm: float
    trim_h_cm: float
    bleed_cm: float
    flap_w_cm: float
    spine_w_cm: float
    hinge_w_cm: float
    safe_inset_cm: float
    mode: str = "wraparound"  # "wraparound" or "embedded" (legacy)

    def pdf_w_pt(self) -> float:
        return (self.trim_w_cm + 2 * self.bleed_cm) * CM_TO_PT

    def pdf_h_pt(self) -> float:
        return (self.trim_h_cm + 2 * self.bleed_cm) * CM_TO_PT

    def trim_w_pt(self) -> float:
        return self.trim_w_cm * CM_TO_PT

    def trim_h_pt(self) -> float:
        return self.trim_h_cm * CM_TO_PT


@dataclass(frozen=True)
class ProductDescriptor:
    """Describes one product offering exposed by a provider."""

    id: str
    label: str
    paper_variants: list[str]
    default_paper_variant: str


@dataclass
class ProviderConfig:
    """User-side selection of provider + product + paper variant."""

    name: str = "peecho"
    product: str = "a4"
    paper_variant: str = "standard"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "product": self.product, "paper_variant": self.paper_variant}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProviderConfig":
        return cls(
            name=data.get("name", "peecho"),
            product=data.get("product", "a4"),
            paper_variant=data.get("paper_variant", "standard"),
        )


@dataclass
class PageOverrides:
    trim_w_cm: Optional[float] = None
    trim_h_cm: Optional[float] = None
    bleed_top_cm: Optional[float] = None
    bleed_bottom_cm: Optional[float] = None
    bleed_outside_cm: Optional[float] = None
    bleed_inside_cm: Optional[float] = None
    safe_inset_outside_cm: Optional[float] = None
    safe_inset_binding_cm: Optional[float] = None
    safe_inset_top_cm: Optional[float] = None
    safe_inset_bottom_cm: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PageOverrides":
        if not data:
            return cls()
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__})


@dataclass
class CoverOverrides:
    flap_w_cm: Optional[float] = None
    spine_w_cm: Optional[float] = None
    hinge_w_cm: Optional[float] = None
    bleed_cm: Optional[float] = None
    safe_inset_cm: Optional[float] = None
    trim_w_cm: Optional[float] = None
    trim_h_cm: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CoverOverrides":
        if not data:
            return cls()
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__})


@dataclass
class RenderingOverrides:
    binding_side_for_odd: str = "left"
    max_pages_per_volume: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {"binding_side_for_odd": self.binding_side_for_odd,
                "max_pages_per_volume": self.max_pages_per_volume}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RenderingOverrides":
        if not data:
            return cls()
        return cls(
            binding_side_for_odd=data.get("binding_side_for_odd", "left") or "left",
            max_pages_per_volume=data.get("max_pages_per_volume"),
        )


@dataclass
class OverridesConfig:
    page: PageOverrides = field(default_factory=PageOverrides)
    cover: CoverOverrides = field(default_factory=CoverOverrides)
    rendering: RenderingOverrides = field(default_factory=RenderingOverrides)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page.to_dict(),
            "cover": self.cover.to_dict(),
            "rendering": self.rendering.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "OverridesConfig":
        if not data:
            return cls()
        return cls(
            page=PageOverrides.from_dict(data.get("page")),
            cover=CoverOverrides.from_dict(data.get("cover")),
            rendering=RenderingOverrides.from_dict(data.get("rendering")),
        )


class Provider(Protocol):
    """Provider protocol. Implementations live in registry.py (data-driven)."""

    name: str
    label: str

    def list_products(self) -> list[ProductDescriptor]: ...
    def page_spec(self, product: str, paper_variant: str) -> PageSpec: ...
    def cover_spec(self, product: str, paper_variant: str, page_count: int) -> CoverSpec: ...
    def validate_page_count(self, product: str, paper_variant: str, page_count: int) -> list[str]: ...
    def supports_embedded_cover(self, product: str) -> bool: ...
