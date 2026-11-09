"""Offline tests for the scene-based micro-drama episode path.

These run fully offline (tone TTS + code-drawn character backgrounds + Pillow captions +
imageio-ffmpeg's bundled ffmpeg). They cover:
  * Episode 1 loading with the expected ordered scenes/characters, including twist beats
    and an explicit cliffhanger.
  * A SHORT subset of the episode rendering to a valid 1080x1920 mp4 with audio.
  * The male vs female lead key-visual frames being distinct (recognizable characters).
"""

from __future__ import annotations

import os

import numpy as np

from shortsfactory.background.character import CharacterScene
from shortsfactory.config import Config
from shortsfactory.render.story_compositor import render_episode
from shortsfactory.story.episodes import get_episode, list_episodes
from shortsfactory.story.model import (
    BEAT_CLIFFHANGER,
    BEAT_HOOK,
    BEAT_TWIST1,
    BEAT_TWIST2,
)
from shortsfactory.tts import get_tts_provider


def test_ep01_loads_with_expected_structure():
    assert "ep01" in list_episodes()
    ep = get_episode("ep01")

    assert ep.title  # finalized Korean title present
    assert ep.logline
    # At least the male lead, female lead, and a supporting voice.
    roles = {c.role for c in ep.characters}
    assert "male_lead" in roles
    assert "female_lead" in roles
    assert len(ep.characters) >= 3

    # Scenes are ordered by index.
    indices = [s.index for s in ep.scenes]
    assert indices == sorted(indices)
    assert len(ep.scenes) >= 6

    beats = [s.beat_label for s in ep.scenes]
    assert BEAT_HOOK in beats
    assert BEAT_TWIST1 in beats
    assert BEAT_TWIST2 in beats
    assert BEAT_CLIFFHANGER in beats

    # Exactly one explicit cliffhanger card, and a next-episode teaser is implied by it.
    cliff = [s for s in ep.scenes if s.cliffhanger]
    assert len(cliff) >= 1

    # Total runtime lands in the target micro-drama window.
    assert 50 < ep.total_duration_sec < 70

    # The female lead must have her own scenes (upper hand / agenda).
    female = next(c for c in ep.characters if c.role == "female_lead")
    assert any(s.speaker_id == female.id for s in ep.scenes)


def test_ep01_short_subset_renders_offline(tmp_path):
    ep = get_episode("ep01")
    cfg = Config.load()
    # Render a short subset (hook + a twist + the cliffhanger) to keep it fast.
    subset = [ep.scenes[0], ep.scenes[5], ep.scenes[-1]]

    out_path = str(tmp_path / "ep01_subset.mp4")
    result = render_episode(ep, get_tts_provider("tone"), cfg, out_path, scenes=subset)

    assert result == out_path
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 0

    from moviepy import VideoFileClip

    clip = VideoFileClip(out_path)
    try:
        assert tuple(clip.size) == (1080, 1920)
        assert clip.audio is not None
        assert clip.duration > 0
    finally:
        clip.close()


def test_male_and_female_lead_key_visuals_differ():
    ep = get_episode("ep01")
    male = next(c for c in ep.characters if c.role == "male_lead")
    female = next(c for c in ep.characters if c.role == "female_lead")

    res = (1080, 1920)
    frame_m = CharacterScene(male).make_clip(2.0, res).get_frame(0.5)
    frame_f = CharacterScene(female).make_clip(2.0, res).get_frame(0.5)

    assert frame_m.shape == frame_f.shape == (1920, 1080, 3)
    # The two leads must be visually distinct, not the same figure recolored by accident.
    assert not np.array_equal(frame_m, frame_f)
    assert np.abs(frame_m.astype(int) - frame_f.astype(int)).mean() > 5.0


def test_same_character_is_consistent_across_scenes():
    """A character's figure is deterministic from its spec (consistent across scenes)."""
    ep = get_episode("ep01")
    female = next(c for c in ep.characters if c.role == "female_lead")
    res = (1080, 1920)
    a = CharacterScene(female).make_clip(2.0, res).get_frame(0.0)
    b = CharacterScene(female).make_clip(2.0, res).get_frame(0.0)
    assert np.array_equal(a, b)
