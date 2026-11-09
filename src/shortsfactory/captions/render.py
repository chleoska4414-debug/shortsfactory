"""Caption rendering with Pillow ONLY.

This module renders word-wrapped, centered, high-contrast captions with a stroke outline
onto transparent RGBA images. It deliberately avoids moviepy's TextClip (which needs
ImageMagick) and any system fonts: it uses the configured TTF or PIL's default font.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


def _load_font(font_path: Optional[str], font_size: int):
    """Load a scalable TrueType font at the requested size.

    Resolution order, every branch honoring ``font_size``:
      1. The explicitly configured ``font_path`` (normally the font vendored with the
         package via Config.font_path).
      2. Pillow's bundled DejaVuSans by name, for installs that ship it.
      3. ImageFont.load_default(font_size) -- the default font, but sized. Passing a size
         is supported on Pillow >= 10.1 and keeps captions legible even when no TTF is
         resolvable. We never call load_default() with no size, which would silently fall
         back to a fixed ~10px bitmap and drop the requested size.
    """
    if font_path:
        try:
            return ImageFont.truetype(font_path, font_size)
        except Exception:
            pass
    # Try Pillow's bundled DejaVuSans by name (works on some installs).
    try:
        return ImageFont.truetype("DejaVuSans.ttf", font_size)
    except Exception:
        pass
    # Last resort: the default font, but still honor the requested size.
    return ImageFont.load_default(font_size)


def _measure(draw: ImageDraw.ImageDraw, text: str, font) -> Tuple[int, int]:
    """Return (width, height) of ``text`` under ``font``."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _wrap_text(
    draw: ImageDraw.ImageDraw, text: str, font, max_width: int
) -> List[str]:
    """Greedy word-wrap ``text`` so each line fits within ``max_width`` pixels."""
    words = text.split()
    if not words:
        return [""]
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        w, _ = _measure(draw, candidate, font)
        if w <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def render_caption(
    text: str,
    size: Tuple[int, int],
    font_path: Optional[str] = None,
    font_size: Optional[int] = None,
    text_color: Tuple[int, int, int, int] = (255, 255, 255, 255),
    stroke_color: Tuple[int, int, int, int] = (0, 0, 0, 255),
    stroke_width: Optional[int] = None,
    line_spacing: int = 14,
    margin_ratio: float = 0.10,
) -> Image.Image:
    """Render ``text`` to a transparent RGBA image of exactly ``size`` (width, height).

    Text is word-wrapped, centered, and drawn with a contrasting stroke so it is readable
    over any background.
    """
    width, height = size
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if font_size is None:
        # Scale font to the frame width so captions are large and legible.
        font_size = max(28, int(width * 0.072))
    if stroke_width is None:
        stroke_width = max(2, font_size // 14)

    font = _load_font(font_path, font_size)

    max_text_width = int(width * (1.0 - 2 * margin_ratio))
    lines = _wrap_text(draw, text or "", font, max_text_width)

    # Measure total block height.
    line_heights = []
    for line in lines:
        _, h = _measure(draw, line or " ", font)
        line_heights.append(h)
    total_height = sum(line_heights) + line_spacing * (len(lines) - 1)

    y = (height - total_height) // 2
    for line, lh in zip(lines, line_heights):
        lw, _ = _measure(draw, line or " ", font)
        x = (width - lw) // 2
        draw.text(
            (x, y),
            line,
            font=font,
            fill=text_color,
            stroke_width=stroke_width,
            stroke_fill=stroke_color,
        )
        y += lh + line_spacing

    return img


def render_segment_overlay(
    text: str,
    resolution: Tuple[int, int],
    font_path: Optional[str] = None,
    band_ratio: float = 0.42,
    bottom_ratio: float = 0.18,
) -> Image.Image:
    """Produce a full-frame RGBA overlay with the caption in the lower-middle band.

    The returned image is the full video resolution so it can be dropped directly onto the
    background as an ImageClip positioned at (0, 0).
    """
    width, height = resolution
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    band_h = int(height * band_ratio)
    caption = render_caption(text, (width, band_h), font_path=font_path)

    # Place the band in the lower-middle, leaving ``bottom_ratio`` of margin below it.
    y = height - int(height * bottom_ratio) - band_h
    y = max(0, y)
    overlay.alpha_composite(caption, (0, y))
    return overlay
