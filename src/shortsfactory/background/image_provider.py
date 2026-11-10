"""AI / supplied character-art path for the micro-drama mode (optional, opt-in).

This module is NEVER exercised by the offline default path or the tests' render. It
sources real "well-drawn manga" character art two ways, both optional, and slots the
result into the SAME compositing hook the offline renderer already has: a Character's
``VisualSpec.asset_image`` PNG (see ``background/character.py``) is composited in place of
the code-drawn figure when that path exists on disk.

  1. User- or pipeline-supplied PNGs on disk, by convention at::

         assets/characters/<episode_id>/<character_id>.png

     ``character_asset_path(episode_id, character_id)`` returns that path, and
     ``load_character_asset(...)`` returns it only if the file exists (else None). These
     files are user content and are kept OUT of the committed tree (see .gitignore).

  2. An AI image-generation path behind a small, extensible provider abstraction. The
     initial backend is OpenAI (``gpt-image-1``, configurable to ``dall-e-3``); the
     string-keyed registry mirrors the other provider registries so a Stable Diffusion or
     other backend can be added later. Every network provider lazily imports its SDK,
     gates on OPENAI_API_KEY, and raises a clear, actionable RuntimeError (naming the env
     var, noting outbound internet is required, and that the offline default needs
     neither) when the key / dependency / network is missing. Network-only blocks are
     marked ``# pragma: no cover``.

CHARACTER-CONSISTENCY STRATEGY
------------------------------
Each character gets a stable, FIXED style prompt (appearance, hair, wardrobe, art style)
plus a deterministic seed so the same character looks the same across every scene and
every episode. The style prompt is taken from ``VisualSpec.style_prompt`` when the author
set one, otherwise it is derived deterministically from the other VisualSpec fields (hair
style/color, wardrobe accent, skin, placement). A per-scene image reuses that same fixed
character style prompt and seed and appends only the situation, so the character stays
on-model while the background/situation changes. Generated images are cached on disk
keyed by (backend, model, prompt, size, seed) so a repeat render never re-bills the API.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Callable, Dict, Optional

from . import image_cache
from ..story.model import VisualSpec

# Documented convention for user/AI-supplied character art.
CHARACTERS_DIR = os.path.join("assets", "characters")

# Default pixel size for a vertical 9:16 character key visual.
DEFAULT_IMAGE_SIZE = "1024x1792"


def character_asset_path(episode_id: str, character_id: str) -> str:
    """Return the conventional PNG path for a character's art in an episode.

    This does not check existence; it only encodes the convention
    ``assets/characters/<episode_id>/<character_id>.png``.
    """
    return os.path.join(CHARACTERS_DIR, episode_id, f"{character_id}.png")


def load_character_asset(episode_id: str, character_id: str) -> Optional[str]:
    """Return the on-disk art path for a character if it exists, else None.

    Offline and side-effect free. The default pipeline does not require any asset.
    """
    path = character_asset_path(episode_id, character_id)
    return path if os.path.exists(path) else None


# -- character-consistency prompt helpers ------------------------------------------------
_HAIR_WORDS = {
    "short": "short neat hair",
    "swept": "short side-swept hair",
    "long": "long flowing hair",
    "bob": "a sleek bob haircut",
    "buzz": "a very short buzz cut",
}


def _rgb_words(rgb) -> str:
    """Describe an (r, g, b) tuple with a coarse human color word for the prompt."""
    r, g, b = (int(c) for c in rgb)
    if max(r, g, b) < 60:
        return "dark"
    if min(r, g, b) > 200:
        return "light"
    if r >= g and r >= b:
        return "warm red-toned"
    if g >= r and g >= b:
        return "green-toned"
    return "cool blue-toned"


def character_style_prompt(visual: VisualSpec) -> str:
    """Return the FIXED style prompt for a character (the consistency anchor).

    Uses ``visual.style_prompt`` verbatim when the author set one; otherwise derives a
    stable description from the deterministic VisualSpec fields so the same character
    always generates the same way. Pure and offline.
    """
    if visual.style_prompt:
        return visual.style_prompt
    hair = _HAIR_WORDS.get((visual.hair_style or "short").lower(), "short neat hair")
    return (
        "high-quality Korean webtoon / manhwa style character portrait, clean line art, "
        f"a single person with {_rgb_words(visual.hair)} {hair}, "
        f"{_rgb_words(visual.skin)} skin tone, wearing {_rgb_words(visual.accent)} "
        "wardrobe, head-and-shoulders bust, vertical composition, consistent character "
        "design"
    )


def character_image_prompt(visual: VisualSpec, extra: str = "") -> str:
    """Compose the full character key-visual prompt from the fixed style + optional extra."""
    base = character_style_prompt(visual)
    return f"{base}. {extra}".strip() if extra else base


def scene_image_prompt(visual: VisualSpec, situation: str) -> str:
    """Compose a per-scene prompt: the SAME fixed character style + the scene situation.

    Keeping the character style prompt fixed and only appending the situation is what
    keeps the character on-model while the background changes across scenes.
    """
    base = character_style_prompt(visual)
    situation = (situation or "").strip()
    if situation:
        return f"{base}. Scene: {situation}"
    return base


# -- provider abstraction + registry -----------------------------------------------------
class ImageProvider(ABC):
    """Base class for character/scene image providers (extensible per backend).

    Implementations generate a PNG for a character key visual (stable per character) and
    for a per-scene situation image, writing the result to disk (via the on-disk cache)
    and returning the path. The offline default never instantiates one of these.
    """

    name: str = "base"

    @abstractmethod
    def generate_character(
        self, visual: VisualSpec, out_path: str, extra: str = ""
    ) -> str:
        """Generate (or reuse cached) a character key-visual PNG; return its path."""
        raise NotImplementedError

    @abstractmethod
    def generate_scene(
        self, visual: VisualSpec, situation: str, out_path: str
    ) -> str:
        """Generate (or reuse cached) a per-scene situation PNG; return its path."""
        raise NotImplementedError


class OpenAIImageProvider(ImageProvider):
    """OpenAI image backend (``gpt-image-1`` by default, configurable to ``dall-e-3``).

    Requires OPENAI_API_KEY and outbound internet, neither of which is available in the
    offline environment. Mirrors ``background/pexels.py``: lazy SDK import, key gate, and a
    clear RuntimeError when the key / dependency / network is missing. Generated images are
    cached under ``assets/cache/`` keyed by (backend, model, prompt, size, seed).
    """

    name = "openai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-image-1",
        size: str = DEFAULT_IMAGE_SIZE,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or "gpt-image-1"
        self.size = size or DEFAULT_IMAGE_SIZE

    def _require_key(self) -> str:
        if not self.api_key:
            raise RuntimeError(
                "The 'openai' image provider requires an OpenAI API key. Set "
                "OPENAI_API_KEY in your .env (and ensure outbound internet access). This "
                "path is billed per image. The offline default draws a code-drawn figure "
                "and needs neither a key nor network; you can also drop art at "
                "assets/characters/<episode>/<character_id>.png instead."
            )
        return self.api_key

    def _generate(self, prompt: str, out_path: str, seed: int) -> str:
        """Return a cached image for ``prompt`` if present, else generate and cache it."""
        self._require_key()
        cached = image_cache.lookup("openai", self.model, prompt, self.size, seed)
        if cached:
            return cached
        data = self._call_openai(prompt)  # network-only; pragma below
        path = image_cache.cache_path("openai", self.model, prompt, self.size, seed)
        image_cache.store(path, data)
        # Also mirror to the caller's requested drop-in path so the asset_image hook finds
        # it at the conventional location.
        if out_path and os.path.abspath(out_path) != os.path.abspath(path):
            image_cache.store(out_path, data)
            return out_path
        return path

    def _call_openai(self, prompt: str) -> bytes:  # pragma: no cover - network provider
        try:
            from openai import OpenAI  # lazy import
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "The 'openai' image provider requires the 'openai' package. Install it "
                "with: pip install 'shortsfactory[providers]'  (or: pip install openai). "
                "The offline default does not need it."
            ) from exc
        try:  # pragma: no cover
            import base64

            client = OpenAI(api_key=self.api_key)
            result = client.images.generate(
                model=self.model, prompt=prompt, size=self.size, n=1
            )
            return base64.b64decode(result.data[0].b64_json)
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI image generation failed. This path needs outbound internet "
                "access, which is not available in offline environments. Supply a PNG at "
                "assets/characters/<episode>/<character_id>.png instead, or run with no "
                f"image flag for the offline figure. Underlying error: {exc}"
            ) from exc

    def generate_character(
        self, visual: VisualSpec, out_path: str, extra: str = ""
    ) -> str:
        prompt = character_image_prompt(visual, extra)
        return self._generate(prompt, out_path, int(visual.seed))

    def generate_scene(self, visual: VisualSpec, situation: str, out_path: str) -> str:
        prompt = scene_image_prompt(visual, situation)
        return self._generate(prompt, out_path, int(visual.seed))


_REGISTRY: Dict[str, Callable[..., ImageProvider]] = {}


def register_image_provider(name: str, factory: Callable[..., ImageProvider]) -> None:
    """Register an image-provider factory under a name."""
    _REGISTRY[name] = factory


def get_image_provider(name: str, **kwargs) -> ImageProvider:
    """Instantiate a registered image provider by name (e.g. 'openai')."""
    key = (name or "").strip().lower()
    if key not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise ValueError(f"Unknown image provider '{name}'. Available: {available}")
    return _REGISTRY[key](**kwargs)


def available_image_providers():
    """Return the sorted names of all registered image providers."""
    return sorted(_REGISTRY)


def _make_openai(api_key=None, model="gpt-image-1", size=DEFAULT_IMAGE_SIZE, **_kw):
    return OpenAIImageProvider(api_key=api_key, model=model, size=size)


register_image_provider("openai", _make_openai)


def generate_character_image(
    prompt: str,
    out_path: str,
    api_key: Optional[str] = None,
    size: str = DEFAULT_IMAGE_SIZE,
    model: str = "gpt-image-1",
    seed: int = 0,
) -> str:
    """Generate character art via OpenAI image generation (optional, network-only).

    PRESERVED public helper (back-compat): mirrors ``background/pexels.py`` and requires an
    OPENAI_API_KEY and outbound network, both unavailable offline. Raises a clear,
    actionable RuntimeError when the key or the dependency/network is missing. Results are
    cached under ``assets/cache/`` so a repeat call with the same prompt/size/seed reuses
    the prior image instead of re-billing. Never called by the default offline path or the
    tests' render.
    """
    provider = OpenAIImageProvider(api_key=api_key, model=model, size=size)
    # Reuses the same key-gate + cache + network path as the provider methods.
    return provider._generate(prompt, out_path, int(seed))
