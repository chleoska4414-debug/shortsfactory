"""Tests for the Pillow caption renderer (no ImageMagick / no TextClip).

These tests guard caption *legibility*, not just "some pixels are drawn". A regression
that drops the configured font or shrinks captions back to the ~10px default bitmap must
make these tests FAIL.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFont

from shortsfactory.captions import render_caption, render_segment_overlay
from shortsfactory.captions.render import _load_font
from shortsfactory.config import Config


def test_default_font_resolves_to_scalable_truetype():
    """Config must resolve a real scalable TTF that shipped with the package."""
    cfg = Config()
    assert cfg.font_path is not None, "no font path resolved; captions would be tiny"
    assert cfg.font_path.endswith(".ttf")

    font = _load_font(cfg.font_path, 77)
    # A real scalable font, not the fixed-size default bitmap.
    assert isinstance(font, ImageFont.FreeTypeFont)
    assert font.size == 77


def test_load_font_honors_requested_size_on_every_branch():
    """Even with no resolvable TTF, the fallback must honor the requested size.

    load_default(font_size) is supported on Pillow >= 10.1 and keeps captions legible.
    """
    # Force the TTF branches to miss so we exercise the default-font fallback.
    font = _load_font("/nonexistent/does-not-exist.ttf", 64)
    assert font.size == 64, "requested font size was silently dropped on fallback"


def test_render_caption_size_and_nontransparent_pixels():
    size = (1080, 800)
    img = render_caption("A readable caption about space facts", size)

    assert isinstance(img, Image.Image)
    assert img.mode == "RGBA"
    assert img.size == size

    arr = np.array(img)
    # Alpha channel must have some opaque pixels (text was drawn).
    assert arr[:, :, 3].max() > 0
    assert int((arr[:, :, 3] > 0).sum()) > 100


def test_render_caption_ink_is_large_and_legible():
    """The rendered text must occupy a meaningful fraction of the frame.

    A ~10px bitmap render of this text would span only ~a few hundred px wide and a
    dozen px tall in a 1080x800 band; the real sized font must be far larger. This is the
    assertion that fails if the font bug ever regresses.
    """
    width, height = 1080, 800
    img = render_caption("Space is almost completely silent", (width, height))
    arr = np.array(img)
    opaque = arr[:, :, 3] > 0

    rows = np.any(opaque, axis=1)
    cols = np.any(opaque, axis=0)
    ink_height = int(rows.sum())
    assert ink_height > 0

    ymin, ymax = int(np.argmax(rows)), int(len(rows) - 1 - np.argmax(rows[::-1]))
    xmin, xmax = int(np.argmax(cols)), int(len(cols) - 1 - np.argmax(cols[::-1]))
    ink_bbox_h = ymax - ymin + 1
    ink_bbox_w = xmax - xmin + 1

    # The caption band is driven by font_size = max(28, width*0.072) ~= 77px per line.
    # A legible render spans far more than the ~10px default bitmap font.
    assert ink_bbox_h >= 60, f"caption text too short ({ink_bbox_h}px); font likely dropped"
    # Centered text should use a wide slice of the frame, not a tiny smudge.
    assert ink_bbox_w >= width * 0.4, f"caption text too narrow ({ink_bbox_w}px)"


def test_render_segment_overlay_full_frame():
    resolution = (1080, 1920)
    overlay = render_segment_overlay("Lower-middle caption text", resolution)
    assert overlay.size == resolution
    arr = np.array(overlay)
    # Caption sits in the lower-middle band, so lower half should have opaque pixels.
    lower_half = arr[arr.shape[0] // 2 :, :, 3]
    assert lower_half.max() > 0
