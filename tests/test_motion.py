"""Offline tests for the beat-aware cinematic motion/camera system.

These prove the micro-drama render path is genuinely dynamic frame to frame (Ken Burns
zoom/pan, breathing sway, blink/mouth idle animation) and that reversal/twist beats
(flash / emphasis / cliffhanger) get a stronger shake + glitch treatment than the calm
HOOK/narration beats, while staying fully deterministic so renders and the committed
sample stay reproducible.

Everything runs offline at the real 1080x1920 output resolution via CharacterScene's
make_clip make_frame hook (no video encoding, so it stays fast).
"""

from __future__ import annotations

import numpy as np

from shortsfactory.background.character import (
    CharacterScene,
    MotionSpec,
    motion_for_scene,
)
from shortsfactory.story.episodes import get_episode
from shortsfactory.story.model import (
    BEAT_CLIFFHANGER,
    BEAT_HOOK,
    BEAT_TWIST1,
    Character,
    Scene,
    VisualSpec,
)

RES = (1080, 1920)  # (width, height) -> frames are (1920, 1080, 3)


def _lead():
    ep = get_episode("ep01")
    return next(c for c in ep.characters if c.role == "male_lead")


def _scene(beat=BEAT_HOOK, kind="narration", **flags):
    return Scene(
        index=flags.pop("index", 0),
        beat_label=beat,
        kind=kind,
        text="모션 테스트 장면",
        target_duration_sec=flags.pop("target_duration_sec", 4.0),
        figure_id="yoojin",
        **flags,
    )


def test_two_frames_of_same_scene_differ_meaningfully():
    """Per-frame animation (zoom/pan/sway) makes distinct timestamps visibly differ."""
    scene = _scene(beat=BEAT_TWIST1, kind="dialog", index=4)
    clip = CharacterScene(_lead(), scene, seed=4).make_clip(4.0, RES)
    a = clip.get_frame(0.1).astype(int)
    b = clip.get_frame(1.5).astype(int)
    assert a.shape == b.shape == (1920, 1080, 3)
    # A real moving camera + idle animation, not the old near-static subtle push.
    assert np.abs(a - b).mean() > 2.0


def test_flash_scene_differs_from_calm_variant_in_shake_window():
    """A flash/emphasis scene gets shake + glitch the calm variant does not."""
    base_lead = _lead()
    flashy = _scene(beat=BEAT_TWIST1, kind="dialog", index=6, emphasis=True, flash=True)
    calm = _scene(beat=BEAT_TWIST1, kind="dialog", index=6)

    f = CharacterScene(base_lead, flashy, seed=6).make_clip(4.0, RES).get_frame(0.05)
    c = CharacterScene(base_lead, calm, seed=6).make_clip(4.0, RES).get_frame(0.05)
    assert f.shape == c.shape == (1920, 1080, 3)
    # Inside the shake/glitch/flash window the two must differ substantially.
    assert np.abs(f.astype(int) - c.astype(int)).mean() > 3.0


def test_frame_shape_stays_exact_under_zoom_and_pan():
    """Output is always exactly (1920, 1080, 3) uint8 regardless of zoom/pan/shake."""
    for beat, flags in [
        (BEAT_HOOK, {}),
        (BEAT_TWIST1, {"emphasis": True}),
        (BEAT_CLIFFHANGER, {"flash": True, "cliffhanger": True}),
    ]:
        scene = _scene(beat=beat, index=1, **flags)
        clip = CharacterScene(_lead(), scene, seed=1).make_clip(4.0, RES)
        for t in (0.0, 0.05, 1.0, 3.9):
            frame = clip.get_frame(t)
            assert frame.shape == (1920, 1080, 3)
            assert frame.dtype == np.uint8


def test_motion_is_deterministic_across_constructions():
    """Same scene + seed yields identical frames across two separate constructions."""
    scene = _scene(beat=BEAT_TWIST1, kind="dialog", index=5, emphasis=True)
    a = CharacterScene(_lead(), scene, seed=5).make_clip(4.0, RES).get_frame(1.2)
    b = CharacterScene(_lead(), scene, seed=5).make_clip(4.0, RES).get_frame(1.2)
    assert np.array_equal(a, b)


def test_motion_for_scene_maps_beats_and_flags():
    """The beat/flag -> motion mapping is tasteful and reversal-aware."""
    assert motion_for_scene(None) == MotionSpec()

    hook = motion_for_scene(_scene(beat=BEAT_HOOK), seed=0)
    assert hook.shake_amp == 0.0 and not hook.glitch

    twist_flash = motion_for_scene(
        _scene(beat=BEAT_TWIST1, emphasis=True, flash=True), seed=6
    )
    assert twist_flash.shake_amp > 0.0
    assert twist_flash.glitch is True
    assert twist_flash.shake_dur > 0.0

    cliff = motion_for_scene(_scene(beat=BEAT_CLIFFHANGER, cliffhanger=True), seed=11)
    assert cliff.glitch is True
    assert cliff.shake_amp >= twist_flash.shake_amp or cliff.shake_amp > 0.0


def test_asset_image_path_skips_blink_mouth_synthesis(tmp_path):
    """When a real art PNG is supplied, the synthesized blink/mouth variants are skipped."""
    from PIL import Image

    asset = tmp_path / "art.png"
    Image.new("RGBA", (400, 600), (0, 200, 255, 255)).save(asset)
    spec = VisualSpec(asset_image=str(asset))
    character = Character(id="z", display_name="Z", role="male_lead", visual=spec)

    scene = _scene(beat=BEAT_TWIST1, kind="dialog", index=2)
    bg = CharacterScene(character, scene, seed=2)
    clip = bg.make_clip(4.0, RES)
    frame = clip.get_frame(0.5)
    assert frame.shape == (1920, 1080, 3)
    # No synthesized face variants were built for the asset path.
    assert bg._figure_blink is None
    assert bg._figure_mouth is None
