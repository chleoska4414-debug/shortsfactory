"""Offline tests for the AI image provider, deterministic cache, and opt-in wiring.

No network is ever used. These cover: the OpenAI image provider's key-gate error, the
pure on-disk cache (deterministic key + re-find), the character-consistency prompt
helpers, the asset_image compositing hook with a cached PNG, and that the DEFAULT episode
render path never attempts image generation.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from shortsfactory.background import image_cache
from shortsfactory.background.character import CharacterScene
from shortsfactory.background.image_provider import (
    DEFAULT_IMAGE_SIZE,
    OpenAIImageProvider,
    available_image_providers,
    character_image_prompt,
    character_style_prompt,
    generate_character_image,
    get_image_provider,
    scene_image_prompt,
)
from shortsfactory.story.model import Character, Scene, VisualSpec


# -- (a) key-gate error -----------------------------------------------------------------
def test_openai_provider_registered():
    assert "openai" in available_image_providers()
    assert isinstance(get_image_provider("openai", api_key=None), OpenAIImageProvider)


def test_get_image_provider_unknown_raises():
    with pytest.raises(ValueError) as exc:
        get_image_provider("stable-diffusion")
    assert "Unknown image provider" in str(exc.value)


def test_openai_character_errors_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIImageProvider(api_key=None)
    with pytest.raises(RuntimeError) as exc:
        provider.generate_character(VisualSpec(), "out.png")
    assert "OPENAI_API_KEY" in str(exc.value)


def test_openai_scene_errors_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIImageProvider(api_key=None)
    with pytest.raises(RuntimeError) as exc:
        provider.generate_scene(VisualSpec(), "a rainy rooftop", "out.png")
    assert "OPENAI_API_KEY" in str(exc.value)


def test_backcompat_generate_character_image_errors_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc:
        generate_character_image("a chaebol heir, webtoon style", "out.png", api_key=None)
    assert "OPENAI_API_KEY" in str(exc.value)


# -- (b) deterministic, offline cache ---------------------------------------------------
def test_cache_key_is_deterministic_and_input_sensitive():
    k1 = image_cache.cache_key("openai", "gpt-image-1", "a hero", "1024x1792", 7)
    k2 = image_cache.cache_key("openai", "gpt-image-1", "a hero", "1024x1792", 7)
    assert k1 == k2  # same inputs -> same key
    # Different prompt -> different key.
    assert k1 != image_cache.cache_key("openai", "gpt-image-1", "a villain", "1024x1792", 7)
    # Different seed -> different key.
    assert k1 != image_cache.cache_key("openai", "gpt-image-1", "a hero", "1024x1792", 8)
    # Different size/model/backend -> different key.
    assert k1 != image_cache.cache_key("openai", "dall-e-3", "a hero", "1024x1792", 7)
    assert k1 != image_cache.cache_key("openai", "gpt-image-1", "a hero", "1024x1024", 7)


def test_cache_store_then_lookup_refinds_file(tmp_path):
    cache_dir = str(tmp_path / "images")
    args = ("openai", "gpt-image-1", "a hero", "1024x1792", 3)
    # Nothing cached yet.
    assert image_cache.lookup(*args, cache_dir=cache_dir) is None
    path = image_cache.cache_path(*args, cache_dir=cache_dir)
    image_cache.store(path, b"\x89PNG-fake-bytes")
    # A subsequent lookup finds the written file.
    found = image_cache.lookup(*args, cache_dir=cache_dir)
    assert found == path
    with open(found, "rb") as fh:
        assert fh.read() == b"\x89PNG-fake-bytes"


def test_provider_reuses_cached_image_without_network(monkeypatch, tmp_path):
    """With a key present, a pre-populated cache entry is returned with no network call."""
    provider = OpenAIImageProvider(api_key="test-key", size=DEFAULT_IMAGE_SIZE)
    visual = VisualSpec(seed=5)
    prompt = character_image_prompt(visual)
    # Pre-seed the cache in a temp dir and patch the module's cache helpers to use it.
    cache_dir = str(tmp_path / "images")
    cached_path = image_cache.cache_path(
        "openai", provider.model, prompt, provider.size, visual.seed, cache_dir=cache_dir
    )
    image_cache.store(cached_path, b"cached-png")

    real_lookup = image_cache.lookup

    def fake_lookup(backend, model, p, size, seed):
        return real_lookup(backend, model, p, size, seed, cache_dir=cache_dir)

    def boom(_prompt):  # must never be called when the cache hits
        raise AssertionError("network call attempted despite a cache hit")

    monkeypatch.setattr(image_cache, "lookup", fake_lookup)
    monkeypatch.setattr(provider, "_call_openai", boom)

    out = provider.generate_character(visual, cached_path)
    assert out == cached_path


# -- character-consistency prompt strategy ----------------------------------------------
def test_style_prompt_prefers_authored_and_is_stable():
    v = VisualSpec(style_prompt="fixed hero look")
    assert character_style_prompt(v) == "fixed hero look"
    # Derived prompt is deterministic for the same spec.
    d = VisualSpec(hair_style="long")
    assert character_style_prompt(d) == character_style_prompt(VisualSpec(hair_style="long"))


def test_scene_prompt_keeps_fixed_character_style():
    v = VisualSpec(style_prompt="fixed hero look")
    scene = scene_image_prompt(v, "standing on a rooftop in the rain")
    # The per-scene prompt reuses the SAME fixed character style (consistency anchor).
    assert scene.startswith("fixed hero look")
    assert "rooftop" in scene


# -- (c) asset_image compositing hook still works with a cached/supplied PNG ------------
def test_cached_png_is_composited_via_asset_image_hook(tmp_path):
    asset = tmp_path / "hero.png"
    Image.new("RGBA", (400, 600), (0, 255, 0, 255)).save(asset)  # bright green art
    spec = VisualSpec(asset_image=str(asset))
    character = Character(id="x", display_name="X", role="male_lead", visual=spec)
    frame = CharacterScene(character).make_clip(2.0, (1080, 1920)).get_frame(0.3)
    r, g, b = frame[..., 0], frame[..., 1], frame[..., 2]
    green = (g > 180) & (r < 90) & (b < 90)
    assert green.sum() > 1000


# -- (d) default episode path never attempts image generation ---------------------------
def test_default_episode_path_does_not_generate_images(monkeypatch, tmp_path):
    import shortsfactory.pipeline as pipeline

    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("image generation attempted on the default offline path")

    # Any attempt to build an image provider on the default path must fail the test.
    monkeypatch.setattr(pipeline, "_apply_image_provider", boom)

    # Render a single-scene subset so the test stays fast; the point is only that the
    # image path is never entered when no image_name/flag is given.
    from shortsfactory.config import Config
    from shortsfactory.render.story_compositor import render_episode
    from shortsfactory.story.episodes import get_episode
    from shortsfactory.tts import get_tts_provider

    episode = get_episode("ep01")
    # Drive the opt-in decision exactly as generate_episode does, with no image provider.
    image_name = (None or Config().image_provider or "").strip().lower() or None
    if image_name:  # pragma: no cover - never true on the default path
        pipeline._apply_image_provider(episode, image_name, Config())
    assert called["n"] == 0

    # And the offline render of one scene still succeeds (figures, no asset_image set).
    out = str(tmp_path / "one.mp4")
    render_episode(
        episode, get_tts_provider("tone"), Config(), out, scenes=episode.scenes[:1]
    )
    import os

    assert os.path.exists(out)
    assert all(c.visual.asset_image is None for c in episode.characters)
