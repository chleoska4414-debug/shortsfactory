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


def _load_series_bible(episode_id: str) -> str:
    """Return the series bible text used as context for an AI episode generator.

    Reads ``stories/<episode_id>/bible.md`` when present (ep01 ships one). Returns an
    empty string if no bible file is found; the AI provider still has the prior
    cliffhanger to work from.
    """
    candidates = [
        os.path.join("stories", episode_id, "bible.md"),
        os.path.join("stories", "ep01", "bible.md"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                continue
    return ""


def _previous_cliffhanger(episode_id: str) -> str:
    """Return a short summary of the prior episode's cliffhanger for AI continuation.

    Uses the authored ep01 cliffhanger scene text when available so an AI provider can
    generate a coherent next episode. Falls back to an empty string (first episode).
    """
    try:
        from .story.episodes import get_episode
        from .story.model import BEAT_CLIFFHANGER

        episode = get_episode(episode_id)
    except Exception:
        return ""
    lines = [s.text for s in episode.scenes if s.beat_label == BEAT_CLIFFHANGER]
    return " ".join(lines).strip()


def generate_episode(
    episode_id: str,
    out_path: str,
    tts_name: Optional[str] = None,
    script_name: Optional[str] = None,
    config: Optional[Config] = None,
) -> str:
    """Render a scene-based micro-drama Episode to ``out_path``.

    By default (no ``script_name``, or 'template') the Episode is loaded from the authored
    data in ``story/episodes.py`` exactly as before. When an AI script provider ('openai'
    or 'anthropic') is selected, the Episode is instead GENERATED from the series bible +
    the prior episode's cliffhanger via that provider's ``generate_episode``. Either way a
    real Episode flows into the same offline scene renderer. The knowledge-card path
    (``generate(topic, n_cards)``) is untouched. Returns the output path.
    """
    from .render.story_compositor import render_episode
    from .story.episodes import get_episode

    config = config or Config.load()
    tts_name = tts_name or config.tts_provider

    # Resolve the Episode: authored data by default, AI-generated when an AI provider is
    # selected. 'template' and None both mean "use the authored episode" (the card
    # 'template' provider has no episode path, so it is not invoked here).
    key = (script_name or "").strip().lower()
    if key in ("openai", "anthropic"):
        provider = get_script_provider(key)
        bible = _load_series_bible(episode_id)
        prev = _previous_cliffhanger(episode_id)
        logger.info("Generating episode via '%s' script provider.", key)
        episode = provider.generate_episode(bible, prev)
    else:
        episode = get_episode(episode_id)
    logger.info(
        "Rendering episode: id=%s title=%s scenes=%d ~%.1fs tts=%s -> %s",
        episode.id,
        episode.title,
        len(episode.scenes),
        episode.total_duration_sec,
        tts_name,
        out_path,
    )

    tts_kwargs = {}
    if tts_name == "edge":
        tts_kwargs["voice"] = config.edge_tts_voice
    tts_provider = get_tts_provider(tts_name, **tts_kwargs)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    result = render_episode(episode, tts_provider, config, out_path)
    logger.info("Done: %s", result)
    return result
