"""Script providers: topic -> narration Script.

Providers are registered in a string-keyed factory. The offline deterministic
'template' provider is registered first and is the guaranteed-available default.
"""

from __future__ import annotations

from typing import Callable, Dict

from .base import Script, ScriptProvider, Segment
from .template import TemplateScriptProvider

_REGISTRY: Dict[str, Callable[[], ScriptProvider]] = {}


def register_script_provider(name: str, factory: Callable[[], ScriptProvider]) -> None:
    """Register a script provider factory under a name."""
    _REGISTRY[name] = factory


def get_script_provider(name: str) -> ScriptProvider:
    """Instantiate a registered script provider by name."""
    key = (name or "").strip().lower()
    if key not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unknown script provider '{name}'. Available: {available}")
    return _REGISTRY[key]()


def available_script_providers():
    """Return the sorted names of all registered script providers."""
    return sorted(_REGISTRY)


# Offline default first.
register_script_provider("template", TemplateScriptProvider)

__all__ = [
    "Script",
    "Segment",
    "ScriptProvider",
    "TemplateScriptProvider",
    "register_script_provider",
    "get_script_provider",
    "available_script_providers",
]
