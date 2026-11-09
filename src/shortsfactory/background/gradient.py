"""Offline default background: an animated vertical gradient rendered with Pillow.

GradientBackground renders a smooth vertical color gradient and gently shifts the hue over
time so the video is not a static image. It produces a moviepy VideoClip from numpy frames,
with no network access and no system media binaries.
"""

from __future__ import annotations

import colorsys
from typing import Tuple

import numpy as np

from .base import BackgroundProvider


class GradientBackground(BackgroundProvider):
    """A smoothly animated vertical gradient sized to the target resolution."""

    def __init__(self, base_hue: float = 0.62, pulse_speed: float = 0.03):
        # base_hue in [0,1]; 0.62 is a calm blue/purple.
        self.base_hue = base_hue
        self.pulse_speed = pulse_speed
        self._cached_wh = None
        self._ramp = None  # cached vertical ramp (height, 1, 1)

    def _frame(self, t: float, width: int, height: int) -> np.ndarray:
        # Hue drifts slowly with time for a subtle animated feel.
        hue_top = (self.base_hue + self.pulse_speed * t) % 1.0
        hue_bottom = (hue_top + 0.12) % 1.0

        top = np.array(colorsys.hsv_to_rgb(hue_top, 0.65, 0.22))
        bottom = np.array(colorsys.hsv_to_rgb(hue_bottom, 0.70, 0.55))

        # Cache the vertical ramp; it only depends on the resolution.
        if self._cached_wh != (width, height):
            self._ramp = np.linspace(0.0, 1.0, height).reshape(height, 1, 1)
            self._cached_wh = (width, height)
        ramp = self._ramp

        # Build a single column, then broadcast across the width (cheap view-based tile).
        col = top.reshape(1, 1, 3) * (1.0 - ramp) + bottom.reshape(1, 1, 3) * ramp
        col = np.clip(col * 255.0, 0, 255).astype("uint8")
        # Broadcast to full width without copying per-pixel math.
        return np.broadcast_to(col, (height, width, 3)).copy()

    def make_clip(self, duration: float, resolution: Tuple[int, int]):
        from moviepy import VideoClip

        width, height = resolution
        duration = max(0.1, float(duration))

        def make_frame(t):
            return self._frame(t, width, height)

        clip = VideoClip(make_frame, duration=duration)
        return clip
