"""Script providers: topic -> narration Script, plus AI episode generators.

Providers are registered in a string-keyed factory. The offline deterministic
'template' provider is registered first and is the guaranteed-available default for the
knowledge-card path (``generate(topic, n_cards) -> Script``).

Two optional NETWORK providers generate a full micro-drama ``Episode`` instead:
'openai' (GPT) and 'anthropic' (Claude). These implement the separate episode path
(``generate_episode(bible, previous_cliffhanger) -> Episode``) and are resolved via lazy
factory functions that import their SDK only when actually called (see
``openai_provider.py`` / ``anthropic_provider.py``). They stay out of the offline default
path; selecting one without its API key raises a clear, actionable RuntimeError.
"""

from __future__ import annotations

import os
from typing import Callable, Dict

from .base import EpisodeGenerator, Script, ScriptProvider, Segment
from .template import TemplateScriptProvider

_REGISTRY: Dict[str, Callable[[], object]] = {}


def register_script_provider(name: str, factory: Callable[[], object]) -> None:
    """Register a script provider factory under a name."""
    _REGISTRY[name] = factory


def get_script_provider(name: str):
    """Instantiate a registered script provider by name.

    Returns a knowledge-card ``ScriptProvider`` ('template') or an ``EpisodeGenerator``
    ('openai' / 'anthropic') depending on the name. The factories are lazy, so the AI SDKs
    are never imported here.
    """
    key = (name or "").strip().lower()
    if key not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unknown script provider '{name}'. Available: {available}")
    return _REGISTRY[key]()


def available_script_providers():
    """Return the sorted names of all registered script providers."""
    return sorted(_REGISTRY)


def _make_openai_provider():
    """Lazy factory for the OpenAI episode generator (SDK imported only when called)."""
    from .openai_provider import OpenAIScriptProvider

    return OpenAIScriptProvider(api_key=os.getenv("OPENAI_API_KEY") or None)


def _make_anthropic_provider():
    """Lazy factory for the Anthropic episode generator (SDK imported only when called)."""
    from .anthropic_provider import AnthropicScriptProvider

    return AnthropicScriptProvider(api_key=os.getenv("ANTHROPIC_API_KEY") or None)


# Offline default first.
register_script_provider("template", TemplateScriptProvider)
# Optional network AI episode generators (lazy; no SDK import at module load time).
register_script_provider("openai", _make_openai_provider)
register_script_provider("anthropic", _make_anthropic_provider)

__all__ = [
    "Script",
    "Segment",
    "ScriptProvider",
    "EpisodeGenerator",
    "TemplateScriptProvider",
    "register_script_provider",
    "get_script_provider",
    "available_script_providers",
]
