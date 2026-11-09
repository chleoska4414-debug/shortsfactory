"""Tests that the default caption font actually covers Korean (Hangul).

The micro-drama deliverable burns Korean dialog and narration into every frame, so the
resolved ``Config.font_path`` MUST render real, distinct Hangul glyphs. The previously
bundled Noto Sans Regular has zero Hangul coverage: every Hangul codepoint rendered as the
identical ``.notdef`` tofu box, so two different Korean strings rasterized byte-identically.

These tests fail if the caption font ever regresses to a non-Korean font. They run fully
offline: no font is downloaded here (the Korean font is vendored into the package at build
time), and nothing touches the network.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from shortsfactory.config import Config


def _render(font: ImageFont.FreeTypeFont, text: str) -> np.ndarray:
    """Rasterize ``text`` with ``font`` onto a grayscale image and return the array."""
    img = Image.new("L", (200, 120), 0)
    ImageDraw.Draw(img).text((8, 8), text, font=font, fill=255)
    return np.array(img)


def test_default_font_is_scalable_truetype():
    """Config must resolve a real scalable TTF that loads as a FreeType font."""
    cfg = Config()
    assert cfg.font_path is not None, "no font path resolved; captions would be tiny"
    assert cfg.font_path.endswith(".ttf")

    font = ImageFont.truetype(cfg.font_path, 60)
    assert isinstance(font, ImageFont.FreeTypeFont)


def test_default_font_renders_distinct_real_hangul():
    """The resolved caption font must render distinct Hangul glyphs, not tofu boxes.

    If the font lacks Hangul coverage, both strings collapse to the identical .notdef box
    and the rasters are byte-identical; this assertion would then FAIL.
    """
    font = ImageFont.truetype(Config().font_path, 60)

    # Two visibly different Hangul strings.
    a = _render(font, "회장님")
    b = _render(font, "편의점")

    # Each must have a sensible amount of ink (real glyphs were drawn, not blanks).
    assert int((a > 0).sum()) > 50, "first Hangul string drew almost no ink"
    assert int((b > 0).sum()) > 50, "second Hangul string drew almost no ink"

    # Real Korean coverage => the two rasters differ. Tofu boxes would be identical.
    assert not np.array_equal(a, b), (
        "distinct Hangul strings rasterized identically; the caption font has no Korean "
        "coverage (regressed to a non-Korean font?)"
    )


def test_single_hangul_glyphs_differ():
    """Two single Hangul syllables must also rasterize differently (glyph-level check)."""
    font = ImageFont.truetype(Config().font_path, 60)
    ga = _render(font, "가")
    other = _render(font, "뷁")
    assert int((ga > 0).sum()) > 20
    assert int((other > 0).sum()) > 20
    assert not np.array_equal(ga, other), "distinct Hangul syllables rendered identically"
