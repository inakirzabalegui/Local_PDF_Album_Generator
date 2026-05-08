"""Apply per-album overrides to base provider specs."""

from __future__ import annotations

from dataclasses import replace

from src.printing.provider import (
    CoverOverrides,
    CoverSpec,
    OverridesConfig,
    PageOverrides,
    PageSpec,
)


def apply_page_overrides(spec: PageSpec, ov: PageOverrides) -> PageSpec:
    return replace(
        spec,
        trim_w_cm=ov.trim_w_cm if ov.trim_w_cm is not None else spec.trim_w_cm,
        trim_h_cm=ov.trim_h_cm if ov.trim_h_cm is not None else spec.trim_h_cm,
        bleed_top_cm=ov.bleed_top_cm if ov.bleed_top_cm is not None else spec.bleed_top_cm,
        bleed_bottom_cm=ov.bleed_bottom_cm if ov.bleed_bottom_cm is not None else spec.bleed_bottom_cm,
        bleed_outside_cm=ov.bleed_outside_cm if ov.bleed_outside_cm is not None else spec.bleed_outside_cm,
        bleed_inside_cm=ov.bleed_inside_cm if ov.bleed_inside_cm is not None else spec.bleed_inside_cm,
        safe_inset_outside_cm=ov.safe_inset_outside_cm if ov.safe_inset_outside_cm is not None else spec.safe_inset_outside_cm,
        safe_inset_binding_cm=ov.safe_inset_binding_cm if ov.safe_inset_binding_cm is not None else spec.safe_inset_binding_cm,
        safe_inset_top_cm=ov.safe_inset_top_cm if ov.safe_inset_top_cm is not None else spec.safe_inset_top_cm,
        safe_inset_bottom_cm=ov.safe_inset_bottom_cm if ov.safe_inset_bottom_cm is not None else spec.safe_inset_bottom_cm,
    )


def apply_cover_overrides(spec: CoverSpec, ov: CoverOverrides) -> CoverSpec:
    return replace(
        spec,
        trim_w_cm=ov.trim_w_cm if ov.trim_w_cm is not None else spec.trim_w_cm,
        trim_h_cm=ov.trim_h_cm if ov.trim_h_cm is not None else spec.trim_h_cm,
        bleed_cm=ov.bleed_cm if ov.bleed_cm is not None else spec.bleed_cm,
        flap_w_cm=ov.flap_w_cm if ov.flap_w_cm is not None else spec.flap_w_cm,
        spine_w_cm=ov.spine_w_cm if ov.spine_w_cm is not None else spec.spine_w_cm,
        hinge_w_cm=ov.hinge_w_cm if ov.hinge_w_cm is not None else spec.hinge_w_cm,
        safe_inset_cm=ov.safe_inset_cm if ov.safe_inset_cm is not None else spec.safe_inset_cm,
    )


def resolve_specs(
    provider_name: str,
    product: str,
    paper_variant: str,
    page_count: int,
    overrides: OverridesConfig,
) -> tuple[PageSpec, CoverSpec]:
    """Resolve final (page, cover) specs by combining provider data + overrides."""
    from src.printing.registry import load_provider

    provider = load_provider(provider_name)
    page = apply_page_overrides(provider.page_spec(product, paper_variant), overrides.page)
    cover = apply_cover_overrides(provider.cover_spec(product, paper_variant, page_count), overrides.cover)
    return page, cover
