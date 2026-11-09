"""Production character-art path: user/AI-supplied PNGs (code + docs only).

This module is NEVER exercised by the offline default path or by the tests. It documents
and implements two ways to source real 'well-drawn manga' character art, both optional:

  1. User- or pipeline-supplied PNGs on disk, by convention at::

         assets/characters/<episode_id>/<character_id>.png

     ``character_asset_path(episode_id, character_id)`` returns that path, and
     ``load_character_asset(...)`` returns it only if the file exists (else None). To use
     real art, set the matching ``Character.visual.asset_image`` to this path; the offline
     CharacterScene renderer will then composite the PNG instead of the code-drawn figure.
     These files are user content and are kept OUT of the committed tree (see .gitignore);
     only the directory convention is documented.

  2. An OpenAI image-generation path, ``generate_character_image(...)``, guarded by
     OPENAI_API_KEY and lazily importing its dependency. It mirrors background/pexels.py:
     with no key / no network it raises a clear, actionable RuntimeError. It is a stub for
     a production pipeline and is never called by the default render or the tests.
"""

from __future__ import annotations

import os
from typing import Optional

# Documented convention for user/AI-supplied character art.
CHARACTERS_DIR = os.path.join("assets", "characters")


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


def generate_character_image(
    prompt: str,
    out_path: str,
    api_key: Optional[str] = None,
    size: str = "1024x1792",
) -> str:
    """Generate character art via OpenAI image generation (optional, network-only).

    Mirrors background/pexels.py: requires an OPENAI_API_KEY and outbound network, both of
    which are unavailable in the offline environment. Raises a clear, actionable
    RuntimeError when the key or the dependency/network is missing. Never called by the
    default offline path or the tests.
    """
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "generate_character_image requires an OpenAI API key. Set OPENAI_API_KEY in "
            "your .env, or place hand-drawn art at "
            "assets/characters/<episode>/<character_id>.png and point the character's "
            "VisualSpec.asset_image at it. The offline default renders a code-drawn figure "
            "and needs neither."
        )
    try:  # pragma: no cover - network provider, never exercised offline
        from openai import OpenAI  # lazy import
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "generate_character_image requires the 'openai' package. Install it with "
            "pip install openai. The offline default does not need it."
        ) from exc

    try:  # pragma: no cover - network provider, never exercised offline
        import base64

        client = OpenAI(api_key=api_key)
        result = client.images.generate(
            model="gpt-image-1", prompt=prompt, size=size, n=1
        )
        b64 = result.data[0].b64_json
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
        with open(out_path, "wb") as fh:
            fh.write(base64.b64decode(b64))
        return out_path
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "OpenAI character-image generation failed. This path needs outbound internet "
            "access, which is not available offline. Supply a PNG at "
            "assets/characters/<episode>/<character_id>.png instead. "
            f"Underlying error: {exc}"
        ) from exc
