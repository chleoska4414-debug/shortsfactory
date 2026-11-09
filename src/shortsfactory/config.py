"""Runtime configuration for shortsfactory.

Config is loaded from environment variables (optionally sourced from a .env file via
python-dotenv). Every field has an offline-safe default so the pipeline works with no
.env present and no network access.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Tuple

from dotenv import load_dotenv


def _default_font_path() -> Optional[str]:
    """Return a path to a usable scalable TTF font, or None to fall back to PIL's default.

    We ship a real TrueType font (Noto Sans) as package data under assets/fonts/ so
    captions always render with a scalable font at the requested size, with no network
    download and no reliance on a system-installed font. Some Pillow builds do not ship a
    bundled DejaVuSans.ttf, so we do not depend on that.

    Resolution order:
      1. The bundled Noto Sans font (always present with the installed package).
      2. Pillow's bundled DejaVuSans.ttf, if this Pillow build provides it.
      3. None -> the caption renderer falls back to ImageFont.load_default(font_size).
    """
    # 1. Font vendored with this package.
    bundled = os.path.join(
        os.path.dirname(__file__), "assets", "fonts", "NotoSans-Regular.ttf"
    )
    if os.path.exists(bundled):
        return bundled

    # 2. Pillow's own bundled font, if available on this build.
    try:
        import PIL

        pil_dir = os.path.dirname(PIL.__file__)
        candidate = os.path.join(pil_dir, "fonts", "DejaVuSans.ttf")
        if os.path.exists(candidate):
            return candidate
    except Exception:
        pass
    return None


@dataclass
class Config:
    """Pipeline configuration with offline-safe defaults."""

    tts_provider: str = "tone"
    bg_provider: str = "gradient"
    script_provider: str = "template"
    resolution: Tuple[int, int] = (1080, 1920)
    fps: int = 30
    edge_tts_voice: str = "en-US-AriaNeural"
    pexels_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    font_path: Optional[str] = field(default_factory=_default_font_path)

    @classmethod
    def load(cls, dotenv_path: Optional[str] = None) -> "Config":
        """Load config from environment, reading a .env file if present.

        All values are optional; defaults keep the offline pipeline functional.
        """
        # load_dotenv is a no-op if the file is absent; never raises.
        load_dotenv(dotenv_path=dotenv_path)

        res_env = os.getenv("RESOLUTION")
        resolution: Tuple[int, int] = (1080, 1920)
        if res_env:
            try:
                w, h = res_env.lower().split("x")
                resolution = (int(w), int(h))
            except Exception:
                resolution = (1080, 1920)

        fps = 30
        try:
            fps = int(os.getenv("FPS", "30"))
        except Exception:
            fps = 30

        font_path = os.getenv("FONT_PATH") or _default_font_path()

        return cls(
            tts_provider=os.getenv("TTS_PROVIDER", "tone") or "tone",
            bg_provider=os.getenv("BG_PROVIDER", "gradient") or "gradient",
            script_provider=os.getenv("SCRIPT_PROVIDER", "template") or "template",
            resolution=resolution,
            fps=fps,
            edge_tts_voice=os.getenv("EDGE_TTS_VOICE", "en-US-AriaNeural")
            or "en-US-AriaNeural",
            pexels_api_key=os.getenv("PEXELS_API_KEY") or None,
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            font_path=font_path,
        )
