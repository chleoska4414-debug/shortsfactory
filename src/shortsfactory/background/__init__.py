"""Background providers: produce the base visual clip.

Providers are registered in a string-keyed factory. The offline 'gradient' provider is
registered first and is the guaranteed-available default. The 'pexels' provider is optional
and requires a key + network.
"""

from __future__ import annotations

from typing import Callable, Dict

from .base import BackgroundProvider
from .gradient import GradientBackground

_REGISTRY: Dict[str, Callable[..., BackgroundProvider]] = {}


def register_bg_provider(name: str, factory: Callable[..., BackgroundProvider]) -> None:
    """Register a background provider factory under a name."""
    _REGISTRY[name] = factory


def get_bg_provider(name: str, **kwargs) -> BackgroundProvider:
    """Instantiate a registered background provider by name."""
    key = (name or "").strip().lower()
    if key not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unknown background provider '{name}'. Available: {available}")
    return _REGISTRY[key](**kwargs)


def available_bg_providers():
    """Return the sorted names of all registered background providers."""
    return sorted(_REGISTRY)


# Offline default first.
register_bg_provider("gradient", lambda **kw: GradientBackground())


def _make_pexels(api_key=None, query="abstract", **_kw) -> BackgroundProvider:
    from .pexels import PexelsBackground

    return PexelsBackground(api_key=api_key, query=query)


register_bg_provider("pexels", _make_pexels)

__all__ = [
    "BackgroundProvider",
    "GradientBackground",
    "register_bg_provider",
    "get_bg_provider",
    "available_bg_providers",
]
