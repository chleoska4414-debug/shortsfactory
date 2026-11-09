"""End-to-end pipeline: topic -> script -> narration -> background -> captions -> mp4."""

from __future__ import annotations

import logging
import os
from typing import Optional

from .background import get_bg_provider
from .config import Config
from .render.compositor import render_video
from .script import get_script_provider
from .tts import get_tts_provider

logger = logging.getLogger("shortsfactory")


def generate(
    topic: str,
    out_path: str,
    tts_name: Optional[str] = None,
    bg_name: Optional[str] = None,
    script_name: Optional[str] = None,
    n_cards: int = 5,
    config: Optional[Config] = None,
) -> str:
    """Generate a short video for ``topic`` and write it to ``out_path``.

    Providers are resolved from their factories; unspecified ones fall back to the
    offline-safe defaults in ``config``. Returns the output path.
    """
    config = config or Config.load()
    tts_name = tts_name or config.tts_provider
    bg_name = bg_name or config.bg_provider
    script_name = script_name or config.script_provider

    logger.info(
        "Generating short: topic=%s script=%s tts=%s bg=%s cards=%s -> %s",
        topic,
        script_name,
        tts_name,
        bg_name,
        n_cards,
        out_path,
    )

    script_provider = get_script_provider(script_name)
    script = script_provider.generate(topic, n_cards)
    logger.info(
        "Script has %d segments, ~%.1fs estimated.",
        len(script.segments),
        script.total_duration_sec,
    )

    tts_kwargs = {}
    if tts_name == "edge":
        tts_kwargs["voice"] = config.edge_tts_voice
    tts_provider = get_tts_provider(tts_name, **tts_kwargs)

    bg_kwargs = {}
    if bg_name == "pexels":
        bg_kwargs["api_key"] = config.pexels_api_key
        bg_kwargs["query"] = topic
    bg_provider = get_bg_provider(bg_name, **bg_kwargs)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    result = render_video(script, tts_provider, bg_provider, out_path, config)
    logger.info("Done: %s", result)
    return result
