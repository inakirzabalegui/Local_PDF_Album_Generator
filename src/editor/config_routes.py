"""REST endpoints powering the Impresión (printing) configuration dialog.

Endpoints:
  GET  /api/providers                         — list available providers.
  GET  /api/providers/<name>                  — products + paper variants.
  GET  /api/config/global                     — current workspace config.
  PUT  /api/config/global                     — persist provider + overrides.
  POST /api/config/preview                    — preview resolved specs without saving.
  GET  /api/workspace/page_count              — current content page count.
"""

from __future__ import annotations

from pathlib import Path

from flask import jsonify, request

from src.editor.app import app
from src.printing.overrides import resolve_specs
from src.printing.provider import OverridesConfig, ProviderConfig
from src.printing.registry import list_providers, load_provider
from src.workspace.config import (
    GlobalConfig,
    read_global_config,
    read_page_configs,
    write_global_config,
)


def _workspace_path() -> Path | None:
    raw = app.config.get("WORKSPACE")
    return Path(raw) if raw else None


def _serialize_page_spec(spec) -> dict:
    return {
        "trim_w_cm": spec.trim_w_cm,
        "trim_h_cm": spec.trim_h_cm,
        "bleed_top_cm": spec.bleed_top_cm,
        "bleed_bottom_cm": spec.bleed_bottom_cm,
        "bleed_outside_cm": spec.bleed_outside_cm,
        "bleed_inside_cm": spec.bleed_inside_cm,
        "safe_inset_outside_cm": spec.safe_inset_outside_cm,
        "safe_inset_binding_cm": spec.safe_inset_binding_cm,
        "safe_inset_top_cm": spec.safe_inset_top_cm,
        "safe_inset_bottom_cm": spec.safe_inset_bottom_cm,
        "max_pages": spec.max_pages,
        "min_pages": spec.min_pages,
        "pdf_w_cm": spec.trim_w_cm + spec.bleed_outside_cm + spec.bleed_inside_cm,
        "pdf_h_cm": spec.trim_h_cm + spec.bleed_top_cm + spec.bleed_bottom_cm,
    }


def _serialize_cover_spec(spec) -> dict:
    return {
        "trim_w_cm": spec.trim_w_cm,
        "trim_h_cm": spec.trim_h_cm,
        "bleed_cm": spec.bleed_cm,
        "flap_w_cm": spec.flap_w_cm,
        "spine_w_cm": spec.spine_w_cm,
        "hinge_w_cm": spec.hinge_w_cm,
        "safe_inset_cm": spec.safe_inset_cm,
        "mode": spec.mode,
        "pdf_w_cm": spec.trim_w_cm + 2 * spec.bleed_cm,
        "pdf_h_cm": spec.trim_h_cm + 2 * spec.bleed_cm,
    }


@app.route("/api/providers", methods=["GET"])
def api_list_providers():
    items = [{"name": n, "label": l} for n, l in list_providers()]
    return jsonify({"providers": items})


@app.route("/api/providers/<name>", methods=["GET"])
def api_provider_detail(name: str):
    try:
        provider = load_provider(name)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    products = []
    for desc in provider.list_products():
        products.append({
            "id": desc.id,
            "label": desc.label,
            "paper_variants": desc.paper_variants,
            "default_paper_variant": desc.default_paper_variant,
        })
    return jsonify({"name": provider.name, "label": provider.label, "products": products})


def _count_content_pages(workspace: Path, cfg: GlobalConfig) -> int:
    pages = read_page_configs(workspace, cfg)
    return sum(1 for p in pages if not p.is_cover and not p.is_backcover)


@app.route("/api/workspace/page_count", methods=["GET"])
def api_page_count():
    ws = _workspace_path()
    if ws is None:
        return jsonify({"error": "No workspace configured"}), 400
    if not (ws / "global_config.yaml").exists():
        return jsonify({"page_count": 0})
    cfg = read_global_config(ws)
    return jsonify({"page_count": _count_content_pages(ws, cfg)})


@app.route("/api/config/global", methods=["GET"])
def api_get_global_config():
    ws = _workspace_path()
    if ws is None:
        return jsonify({"error": "No workspace configured"}), 400
    if not (ws / "global_config.yaml").exists():
        return jsonify({"error": "global_config.yaml missing"}), 404

    cfg = read_global_config(ws)
    page_count = _count_content_pages(ws, cfg)
    page_spec = cfg.page_spec
    cover_spec = cfg.cover_spec(page_count if page_count > 0 else 100)
    provider = load_provider(cfg.provider.name)
    warnings = provider.validate_page_count(cfg.provider.product, cfg.provider.paper_variant, page_count)

    return jsonify({
        "provider": cfg.provider.to_dict(),
        "overrides": cfg.overrides.to_dict(),
        "page_count": page_count,
        "page_spec": _serialize_page_spec(page_spec),
        "cover_spec": _serialize_cover_spec(cover_spec),
        "warnings": warnings,
        "supports_embedded_cover": cfg.supports_embedded_cover(),
    })


@app.route("/api/config/global", methods=["PUT"])
def api_put_global_config():
    ws = _workspace_path()
    if ws is None:
        return jsonify({"error": "No workspace configured"}), 400

    payload = request.get_json() or {}
    provider_data = payload.get("provider", {})
    overrides_data = payload.get("overrides", {})

    # Validate the chosen provider/product/paper_variant exists.
    try:
        provider = load_provider(provider_data.get("name", "peecho"))
        product = provider_data.get("product")
        variants = next((d for d in provider.list_products() if d.id == product), None)
        if variants is None:
            return jsonify({"error": f"Producto '{product}' no existe en provider '{provider.name}'"}), 400
        paper_variant = provider_data.get("paper_variant", variants.default_paper_variant)
        if paper_variant not in variants.paper_variants:
            return jsonify({"error": f"Paper variant '{paper_variant}' no existe en producto '{product}'"}), 400
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 400

    cfg = read_global_config(ws)
    cfg.provider = ProviderConfig.from_dict(provider_data)
    cfg.overrides = OverridesConfig.from_dict(overrides_data)
    write_global_config(ws, cfg)

    return api_get_global_config()


@app.route("/api/config/preview", methods=["POST"])
def api_preview_config():
    """Return resolved specs for an arbitrary provider+overrides combo without saving."""
    payload = request.get_json() or {}
    provider_data = payload.get("provider", {})
    overrides_data = payload.get("overrides", {})
    page_count = int(payload.get("page_count", 0) or 0)

    provider_cfg = ProviderConfig.from_dict(provider_data)
    overrides = OverridesConfig.from_dict(overrides_data)

    try:
        page_spec, cover_spec = resolve_specs(
            provider_cfg.name,
            provider_cfg.product,
            provider_cfg.paper_variant,
            page_count=page_count if page_count > 0 else 100,
            overrides=overrides,
        )
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 400

    provider = load_provider(provider_cfg.name)
    warnings = provider.validate_page_count(provider_cfg.product, provider_cfg.paper_variant, page_count)

    return jsonify({
        "page_spec": _serialize_page_spec(page_spec),
        "cover_spec": _serialize_cover_spec(cover_spec),
        "warnings": warnings,
        "embedded_cover": provider.supports_embedded_cover(provider_cfg.product),
    })
