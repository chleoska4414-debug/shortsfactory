"""Scene-based micro-drama (duanju) story model and episode data.

This package mirrors the data-driven approach of ``content/topics.py``: episodes are
authored as plain Python data (see ``episodes.py``) built from the dataclasses defined in
``model.py``. A scene renderer (``render/story_compositor.py``) turns an ``Episode`` into a
vertical 9:16 mp4 using the same offline building blocks as the knowledge-card path (tone
TTS + Pillow captions + moviepy compositor) plus per-scene character key visuals.
"""

from __future__ import annotations

from .episodes import EPISODES, get_episode, list_episodes
from .model import (
    BEAT_CLIFFHANGER,
    BEAT_HOOK,
    BEAT_TWIST1,
    BEAT_TWIST2,
    Character,
    Episode,
    Scene,
    VisualSpec,
)

__all__ = [
    "Character",
    "Episode",
    "Scene",
    "VisualSpec",
    "BEAT_HOOK",
    "BEAT_TWIST1",
    "BEAT_TWIST2",
    "BEAT_CLIFFHANGER",
    "EPISODES",
    "get_episode",
    "list_episodes",
]
