"""Tests for the offline gradient background provider."""

from __future__ import annotations

import numpy as np

from shortsfactory.background import GradientBackground, get_bg_provider


def test_gradient_clip_duration_and_frame_shape():
    provider = GradientBackground()
    resolution = (1080, 1920)
    clip = provider.make_clip(duration=3.0, resolution=resolution)

    assert abs(clip.duration - 3.0) < 1e-6

    frame = clip.get_frame(0)
    assert isinstance(frame, np.ndarray)
    # moviepy frames are (height, width, 3).
    assert frame.shape == (1920, 1080, 3)
    assert frame.dtype == np.uint8


def test_factory_returns_gradient_default():
    provider = get_bg_provider("gradient")
    assert isinstance(provider, GradientBackground)
