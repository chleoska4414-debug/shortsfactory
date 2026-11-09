"""Offline tests for the code-generated character key-visual background.

Verifies the CharacterScene provider renders a stylized illustrated frame (not a flat
solid color), honors scene direction (rain, breaking-news), composites a supplied asset
PNG when present, and that the production image path errors clearly without a key.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from shortsfactory.background.character import CharacterScene
from shortsfactory.background.image_provider import (
    character_asset_path,
    generate_character_image,
    load_character_asset,
)
from shortsfactory.story.episodes import get_episode
from shortsfactory.story.model import Character, Scene, VisualSpec


def _frame(bg, res=(1080, 1920), t=0.3):
    return bg.make_clip(2.0, res).get_frame(t)


def test_background_is_not_a_flat_solid_color():
    ep = get_episode("ep01")
    male = next(c for c in ep.characters if c.role == "male_lead")
    frame = _frame(CharacterScene(male))
    # A flat fill has near-zero variance; an illustration (gradient + figure + texture +
    # vignette) has substantial spread across the frame.
    assert frame.std() > 12.0
    # The figure occupies a meaningful region distinct from the sky.
    top = frame[: frame.shape[0] // 4].mean()
    bottom = frame[-frame.shape[0] // 4 :].mean()
    assert abs(top - bottom) > 2.0


def test_rain_scene_adds_detail_over_calm_scene():
    ep = get_episode("ep01")
    male = next(c for c in ep.characters if c.role == "male_lead")
    rainy = Scene(index=0, beat_label="HOOK", kind="narration", text="비", target_duration_sec=2.0, figure_id=male.id, rain=True)
    calm = Scene(index=0, beat_label="HOOK", kind="narration", text="비", target_duration_sec=2.0, figure_id=male.id, rain=False)
    rainy_frame = _frame(CharacterScene(male, rainy))
    calm_frame = _frame(CharacterScene(male, calm))
    assert not np.array_equal(rainy_frame, calm_frame)
    # Rain adds bright streaks, raising the overall mean brightness.
    assert rainy_frame.mean() >= calm_frame.mean()


def test_breaking_news_band_renders():
    ep = get_episode("ep01")
    anchor = next(c for c in ep.characters if c.role == "supporting")
    scene = Scene(index=7, beat_label="TWIST 2", kind="dialog", speaker_id=anchor.id,
                  text="속보", target_duration_sec=2.0, breaking_news=True)
    frame = _frame(CharacterScene(anchor, scene))
    assert frame.shape == (1920, 1080, 3)
    # The lower-third band region should be present (non-uniform across that strip).
    strip = frame[int(1920 * 0.70): int(1920 * 0.80)]
    assert strip.std() > 10.0


def test_asset_image_is_composited_when_present(tmp_path):
    # A bright magenta square asset should visibly change the frame vs the code figure.
    asset = tmp_path / "art.png"
    Image.new("RGBA", (400, 600), (255, 0, 255, 255)).save(asset)

    spec = VisualSpec(asset_image=str(asset))
    character = Character(id="x", display_name="X", role="male_lead", visual=spec)
    frame = _frame(CharacterScene(character))
    # Some pixels should be strongly magenta-ish from the composited art.
    r, g, b = frame[..., 0], frame[..., 1], frame[..., 2]
    magenta = (r > 180) & (g < 90) & (b > 180)
    assert magenta.sum() > 1000


def test_character_asset_convention_paths():
    p = character_asset_path("ep01", "haeun")
    assert p.replace("\\", "/") == "assets/characters/ep01/haeun.png"
    # No file present -> None (offline default needs no asset).
    assert load_character_asset("ep01", "haeun") is None


def test_generate_character_image_errors_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    try:
        generate_character_image("a chaebol heir, webtoon style", "/tmp/out.png", api_key=None)
    except RuntimeError as exc:
        assert "OPENAI_API_KEY" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError without an API key")
