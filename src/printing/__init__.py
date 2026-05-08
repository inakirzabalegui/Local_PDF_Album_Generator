"""Modular print-provider system.

Each provider defines page and cover specifications via data files (YAML).
Albums reference a provider+product+paper_variant; per-album overrides allow
fine-grained dimension control without editing provider data.
"""

from src.printing.provider import (
    CoverSpec,
    OverridesConfig,
    PageSpec,
    ProductDescriptor,
    Provider,
    ProviderConfig,
)
from src.printing.registry import load_provider, list_providers

__all__ = [
    "CoverSpec",
    "OverridesConfig",
    "PageSpec",
    "ProductDescriptor",
    "Provider",
    "ProviderConfig",
    "load_provider",
    "list_providers",
]
