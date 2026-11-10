"""Offline, code-generated character key-visual backgrounds (webtoon/anime feel).

CharacterScene draws a STYLIZED illustrated frame with Pillow + numpy - never a plain
solid color. Each frame carries:

  * a per-scene mood gradient (two-stop) with a soft radial glow and a light paper/ink
    texture so the sky reads as an illustration, not a flat fill;
  * a distinct, deterministic stylized character bust (hair shape, accent-colored
    wardrobe, simple face) drawn purely from the character's VisualSpec so the male and
    female leads are clearly different and each character looks the same across scenes;
  * light direction: a vignette always, drifting rain streaks for the rainy hook, and a
    'BREAKING NEWS' lower-third band for the news beat;
  * subtle motion via the moviepy VideoClip make_frame hook (slow push/parallax, drifting
    rain, a brief white flash) so scenes are not static.

If the staged Character has a VisualSpec.asset_image PNG that exists on disk, that image is
composited as the character instead of the code-drawn figure (the hook for real art). This
provider is fully offline and deterministic; it never touches the network.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..story.model import (
    BEAT_CLIFFHANGER,
    BEAT_HOOK,
    BEAT_TWIST1,
    BEAT_TWIST2,
    KIND_DIALOG,
    Character,
    Scene,
    VisualSpec,
)
from .base import BackgroundProvider
from .figure import EXPRESSIONS, render_figure

RGB = Tuple[int, int, int]


@dataclass(frozen=True)
class MotionSpec:
    """Deterministic, beat-aware camera + character motion parameters for one scene.

    Everything here is a plain number so a scene's motion is fully reproducible: given the
    same Scene and seed, ``make_frame(t)`` is a pure function of ``t``. The compositor and
    tests read these to reason about how dynamic a shot should be.

      * ``zoom_start`` / ``zoom_end``   - Ken Burns zoom factors (1.0 == no zoom). A HOOK
        slowly pushes in; twists push harder; some beats pull back for contrast.
      * ``pan_x`` / ``pan_y``           - total normalized camera drift across the scene.
      * ``sway_amp``                    - breathing/handheld sway amplitude in pixels.
      * ``shake_amp`` / ``shake_dur``   - decaying screen-shake amplitude (px) and window.
      * ``glitch``                      - whether a brief RGB-split displacement fires at
        the cut (reversal / twist moments).
      * ``punch_in``                    - extra zoom added during the first ~0.5s (a quick
        'punch-in' on emphasis entries).
    """

    zoom_start: float = 1.0
    zoom_end: float = 1.06
    pan_x: float = 0.0
    pan_y: float = 0.0
    sway_amp: float = 4.0
    shake_amp: float = 0.0
    shake_dur: float = 0.0
    glitch: bool = False
    punch_in: float = 0.0


def motion_for_scene(scene: Optional[Scene], seed: int = 0) -> MotionSpec:
    """Map a Scene's beat label + flags to a deterministic :class:`MotionSpec`.

    The mapping is intentionally tasteful: calm push-in for HOOK/narration, stronger push
    and gentle handheld sway on twists/emphasis, and a short decaying shake + a glitchy
    RGB-split at the cut for reversal/twist moments (flash / emphasis / cliffhanger). Pan
    direction is seeded so alternating scenes drift opposite ways instead of all sliding
    the same direction.
    """
    if scene is None:
        return MotionSpec()

    beat = (scene.beat_label or "").upper()
    # Seeded sign so neighbouring scenes drift in different directions (not a uniform slide).
    sign = 1.0 if (seed % 2 == 0) else -1.0

    if beat == BEAT_HOOK:
        spec = MotionSpec(
            zoom_start=1.0, zoom_end=1.05,
            pan_x=0.018 * sign, pan_y=-0.012,
            sway_amp=3.0,
        )
    elif beat in (BEAT_TWIST1, BEAT_TWIST2):
        spec = MotionSpec(
            zoom_start=1.02, zoom_end=1.09,
            pan_x=0.022 * sign, pan_y=0.010,
            sway_amp=5.0,
        )
    elif beat == BEAT_CLIFFHANGER:
        # Slow, ominous pull-back then settle; strong vignette-ish drift.
        spec = MotionSpec(
            zoom_start=1.10, zoom_end=1.02,
            pan_x=-0.016 * sign, pan_y=0.018,
            sway_amp=3.5,
        )
    else:
        spec = MotionSpec()

    # Reversal / twist-moment emphasis: a short decaying shake, a quick punch-in, and a
    # brief RGB-split glitch at the cut.
    if scene.flash or scene.cliffhanger:
        spec = _replace_motion(
            spec,
            shake_amp=max(spec.shake_amp, 14.0),
            shake_dur=0.45,
            glitch=True,
            punch_in=max(spec.punch_in, 0.05),
            zoom_end=spec.zoom_end + 0.02,
        )
    elif scene.emphasis:
        spec = _replace_motion(
            spec,
            shake_amp=max(spec.shake_amp, 7.0),
            shake_dur=0.30,
            glitch=True,
            punch_in=max(spec.punch_in, 0.04),
        )
    return spec


def _replace_motion(spec: MotionSpec, **changes) -> MotionSpec:
    from dataclasses import replace

    return replace(spec, **changes)


def _lerp(a: RGB, b: RGB, f: float) -> RGB:
    return (
        int(a[0] + (b[0] - a[0]) * f),
        int(a[1] + (b[1] - a[1]) * f),
        int(a[2] + (b[2] - a[2]) * f),
    )


def _gradient(width: int, height: int, top: RGB, bottom: RGB) -> np.ndarray:
    """Vertical two-stop gradient as an (h, w, 3) uint8 array."""
    ramp = np.linspace(0.0, 1.0, height).reshape(height, 1, 1)
    top_a = np.array(top, dtype=np.float64).reshape(1, 1, 3)
    bot_a = np.array(bottom, dtype=np.float64).reshape(1, 1, 3)
    col = top_a * (1.0 - ramp) + bot_a * ramp
    col = np.clip(col, 0, 255).astype("uint8")
    return np.broadcast_to(col, (height, width, 3)).copy()


def _ken_burns(frame: np.ndarray, zoom: float, pan_x: float, pan_y: float) -> np.ndarray:
    """Crop ``frame`` by ``zoom`` with a normalized (pan_x, pan_y) offset, resize back.

    ``zoom`` >= 1.0 selects a centered sub-window of width/height = dim / zoom, shifted by
    ``pan_x``/``pan_y`` (fractions of the full frame), then scales that window back up to
    the original resolution. The output is ALWAYS exactly the input (h, w, 3) so downstream
    compositing is unaffected regardless of zoom/pan magnitude.
    """
    h, w = frame.shape[0], frame.shape[1]
    if zoom <= 1.0001 and pan_x == 0.0 and pan_y == 0.0:
        return frame

    zoom = max(1.0, float(zoom))
    crop_w = max(1, int(round(w / zoom)))
    crop_h = max(1, int(round(h / zoom)))
    max_x = w - crop_w
    max_y = h - crop_h
    # Center the crop, then apply the normalized pan, clamped to stay inside the frame.
    x0 = int(round(max_x / 2.0 + pan_x * w))
    y0 = int(round(max_y / 2.0 + pan_y * h))
    x0 = min(max(x0, 0), max_x)
    y0 = min(max(y0, 0), max_y)

    window = frame[y0:y0 + crop_h, x0:x0 + crop_w, :]
    img = Image.fromarray(np.clip(window, 0, 255).astype("uint8"))
    img = img.resize((w, h), Image.BILINEAR)
    return np.asarray(img, dtype=np.float64)


class CharacterScene(BackgroundProvider):
    """Render a stylized character key visual for a single scene, with subtle motion."""

    def __init__(
        self,
        character: Optional[Character],
        scene: Optional[Scene] = None,
        seed: int = 0,
    ):
        self.character = character
        self.scene = scene
        self.seed = seed
        self._visual: VisualSpec = (
            character.visual if character is not None else VisualSpec()
        )
        # Resolve the scene palette (scene override wins over the character's default).
        top = self._visual.palette_top
        bottom = self._visual.palette_bottom
        if scene is not None and scene.palette_top is not None:
            top = scene.palette_top
        if scene is not None and scene.palette_bottom is not None:
            bottom = scene.palette_bottom
        self._palette_top = top
        self._palette_bottom = bottom

        # Pre-compute a deterministic rain field so streaks drift smoothly over time.
        rng = np.random.default_rng(1234 + seed)
        self._rain_x = rng.random(140)
        self._rain_y = rng.random(140)
        self._rain_len = rng.uniform(0.02, 0.06, 140)

        # Pre-render the static character layer (figure + texture-free illustration bits)
        # once per resolution; motion is applied as cheap transforms per frame.
        self._cached_wh: Optional[Tuple[int, int]] = None
        self._figure_rgba: Optional[Image.Image] = None
        # Idle-animation variants (code-drawn figure only): eyes-closed (blink) and
        # mouth-open (speaking). None when a real art PNG is supplied.
        self._figure_blink: Optional[Image.Image] = None
        self._figure_mouth: Optional[Image.Image] = None
        self._has_drawn_face: bool = self._asset_image_path() is None
        self._base_rgb: Optional[np.ndarray] = None
        self._fig_cache: dict = {}

    # -- asset image hook ---------------------------------------------------------------
    def _asset_image_path(self) -> Optional[str]:
        spec = self._visual
        if spec.asset_image and os.path.exists(spec.asset_image):
            return spec.asset_image
        return None

    # -- illustration primitives --------------------------------------------------------
    def _draw_figure(
        self,
        width: int,
        height: int,
        eyes_closed: bool = False,
        mouth_open: bool = False,
    ) -> Image.Image:
        """Draw the stylized character bust as a transparent RGBA layer.

        The figure is a clean vector-style bust: shoulders in the accent wardrobe color, a
        neck, a head with a simple face, and a hair silhouette whose shape is chosen by the
        VisualSpec.hair_style token. All geometry is derived from the spec so each
        character is distinct and reproducible.

        ``eyes_closed`` / ``mouth_open`` select idle-animation variants (eye-blink and a
        small speaking mouth). They only affect the code-drawn figure; a supplied art PNG
        is composited verbatim and ignores them.
        """
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        spec = self._visual
        # If a real art PNG is supplied, composite it centered and return early.
        asset = self._asset_image_path()
        if asset:
            try:
                art = Image.open(asset).convert("RGBA")
                # Fit to ~80% width, anchored near the lower third.
                target_w = int(width * 0.8)
                ratio = target_w / art.width
                target_h = int(art.height * ratio)
                art = art.resize((target_w, target_h), Image.LANCZOS)
                x = int(width * spec.anchor_x) - target_w // 2
                y = int(height * 0.58) - target_h // 2
                layer.alpha_composite(art, (max(0, x), max(0, y)))
                return layer
            except Exception:
                # Fall through to the code-drawn figure if the asset is unreadable.
                pass

        role = self.character.role if self.character is not None else "supporting"
        figure = render_figure(
            spec, role, width, height,
            expression=self._expression(),
            eyes_closed=eyes_closed, mouth_open=mouth_open,
            cache=self._fig_cache,
        )

        if self.scene and self.scene.reveal_photo:
            self._draw_torn_card(figure)
        return figure

    def _draw_torn_card(self, figure: Image.Image) -> None:
        draw = ImageDraw.Draw(figure)
        width, height = figure.size
        x = width * self._visual.anchor_x
        r = width * 0.16
        y = height * 0.385 + r * 1.18

        def points(vertices):
            return [(x + r * dx, y + r * dy) for dx, dy in vertices]

        ink = (55, 31, 31)
        # Ragged edge at the end of the business card, just above her fingers.
        draw.polygon(points([(-2.07, -0.10), (-1.59, -0.29), (-1.63, -0.12),
                             (-1.55, -0.04), (-1.65, 0.03), (-1.62, 0.17),
                             (-1.93, 0.26)]), fill=(248, 234, 209), outline=ink, width=max(1, int(r * 0.018)))
        draw.line(points([(-1.96, -0.04), (-1.75, -0.13)]), fill=ink, width=max(1, int(r * 0.025)))

    @staticmethod
    def _photo_sprite(r: float) -> np.ndarray:
        photo = Image.new("RGBA", (max(1, round(r * 0.76)), max(1, round(r * 0.84))))
        draw = ImageDraw.Draw(photo)

        def points(vertices):
            return [(r * x, r * y) for x, y in vertices]

        draw.polygon(points([(0.19, 0.01), (0.74, 0.17), (0.56, 0.80), (0.01, 0.64)]),
                     fill=(247, 222, 174), outline=(55, 31, 31), width=max(1, int(r * 0.023)))
        draw.polygon(points([(0.23, 0.09), (0.66, 0.22), (0.53, 0.69), (0.11, 0.56)]),
                     fill=(126, 88, 61))
        draw.polygon(points([(0.28, 0.22), (0.51, 0.28), (0.47, 0.43), (0.34, 0.53), (0.25, 0.38)]),
                     fill=(239, 201, 124))
        return np.asarray(photo, dtype=np.float64)

    def _expression(self) -> str:
        """Pick the facial expression from the scene (explicit override, else beat/flags)."""
        sc = self.scene
        if sc is None:
            return "neutral"
        if sc.expression in EXPRESSIONS:
            return sc.expression
        if sc.flash and (sc.beat_label or "").upper() == BEAT_CLIFFHANGER:
            return "angry"
        if sc.cliffhanger or sc.flash:
            return "shock"
        if sc.emphasis:
            return "resigned" if sc.kind != KIND_DIALOG else "angry"
        if sc.rain:
            return "worried"
        return "neutral"

    def _add_props(self, base: np.ndarray, width: int, height: int) -> np.ndarray:
        """Tiny set pieces behind the figure: a rainy street lamp or convenience-store shelves."""
        sc = self.scene
        if sc is None or sc.breaking_news:
            return base
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        dark = _lerp(self._palette_bottom, (0, 0, 0), 0.35)
        if sc.rain:
            x = int(width * 0.12)
            d.rectangle([x - 8, int(height * 0.22), x + 8, height], fill=dark + (255,))
            d.rectangle([x - 8, int(height * 0.22), x + 150, int(height * 0.22) + 14], fill=dark + (255,))
            d.rounded_rectangle([x + 110, int(height * 0.22) + 8, x + 190, int(height * 0.22) + 40],
                                radius=12, fill=(255, 226, 150, 255))
            layer = layer.filter(ImageFilter.GaussianBlur(2.5))
            arr = np.asarray(layer, dtype=np.float64)
            a = arr[:, :, 3:4] / 255.0
            base = base * (1.0 - a * 0.9) + arr[:, :, :3] * a * 0.9
            yy, xx = np.mgrid[0:height, 0:width]
            gx, gy = x + 150, int(height * 0.22) + 24
            glow = np.exp(-(((xx - gx) / (width * 0.32)) ** 2 + ((yy - gy) / (height * 0.2)) ** 2))
            return base + glow.reshape(height, width, 1) * np.array([70.0, 58.0, 30.0]).reshape(1, 1, 3)
        beat = (sc.beat_label or "").upper()
        if beat in (BEAT_TWIST1, BEAT_TWIST2):
            rng = np.random.default_rng(4242 + self.seed)
            lighter = _lerp(self._palette_top, (255, 255, 255), 0.18)
            for row, y in enumerate((0.20, 0.31, 0.42)):
                yy = int(height * y)
                d.rectangle([0, yy, width, yy + 10], fill=dark + (255,))
                x = int(width * 0.02)
                while x < width:
                    bw = int(rng.integers(34, 80))
                    bh = int(rng.integers(50, 92))
                    col = lighter if rng.random() < 0.5 else _lerp(self._palette_top, (0, 0, 0), 0.2)
                    d.rectangle([x, yy - bh, x + bw, yy], fill=col + (255,))
                    x += bw + int(rng.integers(6, 18))
            layer = layer.filter(ImageFilter.GaussianBlur(4))
            arr = np.asarray(layer, dtype=np.float64)
            a = arr[:, :, 3:4] / 255.0 * 0.55
            return base * (1.0 - a) + arr[:, :, :3] * a
        return base

    def _texture(self, width: int, height: int) -> np.ndarray:
        """A faint deterministic grain so the sky reads as illustration, not a flat fill."""
        rng = np.random.default_rng(99 + self.seed)
        noise = rng.normal(0.0, 7.0, (height // 6, width // 6, 1))
        small = Image.fromarray(np.clip(noise + 128, 0, 255).astype("uint8")[:, :, 0])
        grain = np.array(small.resize((width, height), Image.BILINEAR)).astype(np.float64)
        return (grain - 128.0).reshape(height, width, 1)

    def _vignette(self, width: int, height: int) -> np.ndarray:
        yy, xx = np.mgrid[0:height, 0:width]
        cx, cy = width / 2.0, height * 0.46
        d = np.sqrt(((xx - cx) / (width * 0.75)) ** 2 + ((yy - cy) / (height * 0.62)) ** 2)
        v = np.clip(1.0 - (d - 0.6) * 0.9, 0.35, 1.0)
        return v.reshape(height, width, 1)

    def _build_base(self, width: int, height: int):
        base = _gradient(width, height, self._palette_top, self._palette_bottom).astype(np.float64)

        # Soft radial glow around the figure to give the illustration a focal point.
        yy, xx = np.mgrid[0:height, 0:width]
        gx = width * (self._visual.anchor_x)
        gy = height * 0.40
        glow = np.exp(-(((xx - gx) / (width * 0.5)) ** 2 + ((yy - gy) / (height * 0.33)) ** 2))
        glow = glow.reshape(height, width, 1)
        glow_color = np.array(_lerp(self._palette_top, (255, 255, 255), 0.25), dtype=np.float64)
        base = base * (1.0 - 0.28 * glow) + glow_color.reshape(1, 1, 3) * (0.28 * glow)

        base = self._add_props(base, width, height)
        base += self._texture(width, height)
        base *= self._vignette(width, height)
        base = np.clip(base, 0, 255)

        self._base_rgb = base
        self._figure_rgba = self._draw_figure(width, height)
        if self._has_drawn_face:
            # Pre-render blink / speaking variants once; selected per-frame at render time.
            self._figure_blink = self._draw_figure(width, height, eyes_closed=True)
            self._figure_mouth = self._draw_figure(width, height, mouth_open=True)
        else:
            self._figure_blink = None
            self._figure_mouth = None
        self._cached_wh = (width, height)

    def _rain_overlay(self, t: float, width: int, height: int) -> np.ndarray:
        """Return an (h, w, 3) additive rain layer that drifts with time."""
        layer = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(layer)
        drift = (t * 0.9) % 1.0
        for i in range(self._rain_x.size):
            x = int(((self._rain_x[i] + 0.03 * i) % 1.0) * width)
            y = int(((self._rain_y[i] + drift) % 1.0) * height)
            ln = int(self._rain_len[i] * height)
            draw.line([x, y, x - int(ln * 0.3), y + ln], fill=120, width=2)
        arr = np.array(layer).astype(np.float64).reshape(height, width, 1)
        return np.broadcast_to(arr * 0.6, (height, width, 3))

    def _breaking_news_band(self, width: int, height: int) -> Image.Image:
        """A BREAKING-NEWS banner as a transparent RGBA overlay.

        The banner is anchored near the TOP of the frame (an upper-third news strip)
        rather than the lower third, so it never collides with the lower-third dialog
        caption and speaker label drawn by the story compositor. A thin accent rule sits
        just above and below the strip to read as a broadcast chyron.
        """
        band = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(band)
        band_h = int(height * 0.10)
        y0 = int(height * 0.12)
        red = self._visual.accent
        # Red tag + dark strip.
        draw.rectangle([0, y0, width, y0 + band_h], fill=(16, 16, 20, 235))
        tag_w = int(width * 0.46)
        draw.rectangle([0, y0, tag_w, y0 + band_h], fill=(red[0], red[1], red[2], 255))
        font = _load_label_font(int(band_h * 0.46))
        draw.text((int(width * 0.04), y0 + int(band_h * 0.26)), "속보 BREAKING",
                  font=font, fill=(255, 255, 255, 255))
        # Thin accent rules above and below the strip.
        draw.rectangle([0, y0 - 6, width, y0], fill=(red[0], red[1], red[2], 255))
        draw.rectangle([0, y0 + band_h, width, y0 + band_h + 6],
                       fill=(red[0], red[1], red[2], 255))
        return band

    def make_clip(self, duration: float, resolution: Tuple[int, int]):
        from moviepy import VideoClip

        width, height = resolution
        duration = max(0.1, float(duration))
        dur = max(duration, 0.1)
        scene = self.scene
        rain = bool(scene and scene.rain)
        breaking = bool(scene and scene.breaking_news)
        flash = bool(scene and scene.flash)
        is_dialog = bool(scene and scene.kind == KIND_DIALOG)

        if self._cached_wh != (width, height):
            self._build_base(width, height)
        breaking_band = self._breaking_news_band(width, height) if breaking else None

        # Deterministic, beat-aware camera + character motion for this scene.
        motion = motion_for_scene(scene, self.seed)
        # Arrays cached once so make_frame stays cheap per frame.
        fig_open = np.asarray(self._figure_rgba, dtype=np.float64)
        fig_blink = (
            np.asarray(self._figure_blink, dtype=np.float64)
            if self._figure_blink is not None else None
        )
        fig_mouth = (
            np.asarray(self._figure_mouth, dtype=np.float64)
            if self._figure_mouth is not None else None
        )
        r = width * 0.16
        photo = self._photo_sprite(r) if scene and scene.reveal_photo else None
        photo_x = width * self._visual.anchor_x - r * 1.76
        photo_y = height * 0.385 + r * 1.50
        # Seeded phase offsets so neighbouring scenes don't breathe/blink in lockstep.
        rng = np.random.default_rng(777 + self.seed)
        sway_phase = float(rng.uniform(0.0, 2.0 * math.pi))
        blink_offset = float(rng.uniform(0.0, 1.6))
        blink_period = 2.6 + float(rng.uniform(0.0, 1.4))

        def _select_figure(t: float) -> np.ndarray:
            """Pick the idle-animation figure variant (blink / speaking) for time ``t``."""
            if not self._has_drawn_face:
                return fig_open
            # Eye-blink: eyes shut for ~0.12s every blink_period seconds.
            phase = (t + blink_offset) % blink_period
            if fig_blink is not None and phase < 0.12:
                return fig_blink
            # Speaking mouth on dialog scenes: oscillate open/closed at a natural cadence.
            if is_dialog and fig_mouth is not None:
                if math.sin(t * 11.0 + sway_phase) > 0.35:
                    return fig_mouth
            return fig_open

        def make_frame(t: float) -> np.ndarray:
            frame = self._base_rgb.copy()

            # Subtle slow push: brighten slightly over the scene for a 'breathing' feel.
            push = 1.0 + 0.04 * math.sin((t / dur) * math.pi)
            frame = np.clip(frame * push, 0, 255)

            # --- character idle motion -------------------------------------------------
            # Breathing sway: a slow vertical + horizontal oscillation (handheld feel).
            sway_y = int(round(motion.sway_amp * math.sin(t * 1.5 + sway_phase)))
            sway_x = int(round(motion.sway_amp * 0.4 * math.sin(t * 0.9 + sway_phase)))
            fig_arr = _select_figure(t)
            if sway_y:
                fig_arr = np.roll(fig_arr, sway_y, axis=0)
            if sway_x:
                fig_arr = np.roll(fig_arr, sway_x, axis=1)
            alpha = fig_arr[:, :, 3:4] / 255.0
            frame = frame * (1.0 - alpha) + fig_arr[:, :, :3] * alpha

            if photo is not None:
                fall = min(1.0, max(0.0, (t - 0.55) / 0.85)) ** 2
                px = int(photo_x + sway_x + r * 0.15 * fall)
                py = int(photo_y + sway_y + r * 0.42 * fall)
                x0, y0 = max(0, px), max(0, py)
                x1, y1 = min(width, px + photo.shape[1]), min(height, py + photo.shape[0])
                if x1 > x0 and y1 > y0:
                    patch = photo[y0 - py:y1 - py, x0 - px:x1 - px]
                    opacity = patch[:, :, 3:4] / 255
                    frame[y0:y1, x0:x1] = frame[y0:y1, x0:x1] * (1 - opacity) + patch[:, :, :3] * opacity

            if rain:
                frame = np.clip(frame + self._rain_overlay(t, width, height), 0, 255)

            if breaking_band is not None:
                b = np.asarray(breaking_band, dtype=np.float64)
                ba = b[:, :, 3:4] / 255.0
                frame = frame * (1.0 - ba) + b[:, :, :3] * ba

            # --- Ken Burns zoom + pan + handheld/shake camera --------------------------
            prog = t / dur
            zoom = motion.zoom_start + (motion.zoom_end - motion.zoom_start) * prog
            # Quick punch-in over the first ~0.5s on emphasis entries.
            if motion.punch_in and t < 0.5:
                zoom += motion.punch_in * (1.0 - t / 0.5)
            zoom = max(1.0, zoom)
            pan_x = motion.pan_x * prog
            pan_y = motion.pan_y * prog
            # Decaying screen shake inside the shake window (reversal/twist moments).
            if motion.shake_amp and t < motion.shake_dur:
                decay = 1.0 - (t / motion.shake_dur)
                pan_x += (motion.shake_amp / width) * decay * math.sin(t * 90.0)
                pan_y += (motion.shake_amp / height) * decay * math.sin(t * 77.0 + 1.3)
            frame = _ken_burns(frame, zoom, pan_x, pan_y)

            # --- brief RGB-split glitch at the cut (reversal emphasis) -----------------
            if motion.glitch and t < 0.18:
                shift = int(round(10 * (1.0 - t / 0.18)))
                if shift:
                    frame = frame.copy()
                    frame[:, :, 0] = np.roll(frame[:, :, 0], shift, axis=1)
                    frame[:, :, 2] = np.roll(frame[:, :, 2], -shift, axis=1)

            if flash and t < 0.35:
                f = (0.35 - t) / 0.35
                frame = np.clip(frame + 200.0 * f, 0, 255)

            return np.clip(frame, 0, 255).astype("uint8")

        return VideoClip(make_frame, duration=duration)


# -- label font helper (kept local so captions/render.py stays caption-only) -------------
def _load_label_font(size: int):
    from ..config import Config

    font_path = Config().font_path
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default(size)
