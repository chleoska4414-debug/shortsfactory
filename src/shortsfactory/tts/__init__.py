"""TTS providers: text -> narration audio.

Providers are registered in a string-keyed factory. The offline 'tone' provider is
registered first and is the guaranteed-available default. Network providers ('edge',
'gtts') are optional, lazily importing their dependencies.
"""

from __future__ import annotations

from typing import Callable, Dict

from .base import TTSProvider
from .tone import ToneTTS

_REGISTRY: Dict[str, Callable[..., TTSProvider]] = {}


def register_tts_provider(name: str, factory: Callable[..., TTSProvider]) -> None:
    """Register a TTS provider factory under a name."""
    _REGISTRY[name] = factory


def get_tts_provider(name: str, **kwargs) -> TTSProvider:
    """Instantiate a registered TTS provider by name.

    Optional kwargs (e.g. voice for edge) are forwarded to the factory.
    """
    key = (name or "").strip().lower()
    if key not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unknown TTS provider '{name}'. Available: {available}")
    return _REGISTRY[key](**kwargs)


def available_tts_providers():
    """Return the sorted names of all registered TTS providers."""
    return sorted(_REGISTRY)


# Offline default first.
register_tts_provider("tone", lambda **kw: ToneTTS())


def _make_edge(voice: str = "en-US-AriaNeural", **_kw) -> TTSProvider:
    from .edge import EdgeTTS

    return EdgeTTS(voice=voice)


def _make_gtts(lang: str = "en", **_kw) -> TTSProvider:
    from .gtts_provider import GTTSProvider

    return GTTSProvider(lang=lang)


def _make_windows_korean(**_kw) -> TTSProvider:
    from .windows_korean import WindowsKoreanTTS

    return WindowsKoreanTTS()


register_tts_provider("windows-ko", _make_windows_korean)
register_tts_provider("edge", _make_edge)
register_tts_provider("gtts", _make_gtts)

__all__ = [
    "TTSProvider",
    "ToneTTS",
    "register_tts_provider",
    "get_tts_provider",
    "available_tts_providers",
]
