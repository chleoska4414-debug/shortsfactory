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
from PIL import Image, ImageDraw, ImageFont

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

        draw = ImageDraw.Draw(layer)

        cx = int(width * spec.anchor_x)
        # Head geometry.
        head_r = int(width * 0.16)
        head_cy = int(height * 0.40)
        head_cx = cx

        # Shoulders / torso (accent wardrobe). A rounded trapezoid-ish bust.
        shoulder_w = int(width * 0.62)
        torso_top = head_cy + int(head_r * 0.9)
        torso_bottom = int(height * 0.92)
        accent = spec.accent
        accent_dark = _lerp(accent, (0, 0, 0), 0.35)
        # Body as a big rounded rectangle, with a darker inner panel for depth.
        draw.rounded_rectangle(
            [cx - shoulder_w // 2, torso_top, cx + shoulder_w // 2, torso_bottom],
            radius=int(width * 0.14),
            fill=accent,
        )
        draw.rounded_rectangle(
            [cx - shoulder_w // 6, torso_top + int(head_r * 0.2), cx + shoulder_w // 6, torso_bottom],
            radius=int(width * 0.06),
            fill=accent_dark,
        )

        # Neck.
        neck_w = int(head_r * 0.7)
        draw.rounded_rectangle(
            [head_cx - neck_w // 2, head_cy + int(head_r * 0.4),
             head_cx + neck_w // 2, torso_top + int(head_r * 0.2)],
            radius=neck_w // 3,
            fill=spec.skin,
        )

        # Head (face).
        draw.ellipse(
            [head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r],
            fill=spec.skin,
        )

        # Simple face features (eyes + subtle mouth) in a soft ink tone.
        ink = _lerp(spec.hair, (0, 0, 0), 0.2)
        eye_dy = int(head_r * 0.12)
        eye_dx = int(head_r * 0.42)
        eye_r = max(3, int(head_r * 0.10))
        lid = max(2, eye_r // 2)
        for sgn in (-1, 1):
            ex = head_cx + sgn * eye_dx
            ey = head_cy + eye_dy
            if eyes_closed:
                # A blink: a short lid line instead of the open eye.
                draw.line([ex - eye_r, ey, ex + eye_r, ey], fill=ink, width=lid)
            else:
                draw.ellipse([ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r], fill=ink)
        # Mouth: a thin closed line, or a small open ellipse while speaking.
        mouth_w = int(head_r * 0.34)
        my = head_cy + int(head_r * 0.52)
        mouth_col = _lerp(spec.skin, (120, 40, 40), 0.5)
        if mouth_open:
            mh = max(3, int(head_r * 0.14))
            draw.ellipse(
                [head_cx - mouth_w // 2, my - mh, head_cx + mouth_w // 2, my + mh],
                fill=_lerp(spec.skin, (90, 30, 30), 0.65),
            )
        else:
            draw.line(
                [head_cx - mouth_w // 2, my, head_cx + mouth_w // 2, my],
                fill=mouth_col,
                width=max(2, head_r // 18),
            )

        # Hair silhouette, shape driven by the style token so characters differ.
        self._draw_hair(draw, spec, head_cx, head_cy, head_r, height)

        return layer

    def _draw_hair(self, draw, spec: VisualSpec, cx: int, cy: int, r: int, height: int):
        hair = spec.hair
        style = (spec.hair_style or "short").lower()

        if style == "long":
            # Long hair framing the face and falling past the shoulders.
            draw.ellipse([cx - int(r * 1.15), cy - int(r * 1.15),
                          cx + int(r * 1.15), cy + int(r * 0.35)], fill=hair)
            # Side falls.
            draw.rounded_rectangle(
                [cx - int(r * 1.15), cy - int(r * 0.2), cx - int(r * 0.55), cy + int(r * 2.4)],
                radius=int(r * 0.4), fill=hair)
            draw.rounded_rectangle(
                [cx + int(r * 0.55), cy - int(r * 0.2), cx + int(r * 1.15), cy + int(r * 2.4)],
                radius=int(r * 0.4), fill=hair)
            # Re-expose the face oval.
            draw.ellipse([cx - int(r * 0.85), cy - int(r * 0.7),
                          cx + int(r * 0.85), cy + int(r * 1.0)], fill=spec.skin)
        elif style == "swept":
            # Short, side-swept corporate hair: an asymmetric cap.
            draw.ellipse([cx - int(r * 1.12), cy - int(r * 1.2),
                          cx + int(r * 1.12), cy + int(r * 0.1)], fill=hair)
            # Sweep a fringe to one side by carving the forehead back in.
            draw.pieslice([cx - int(r * 0.95), cy - int(r * 0.95),
                           cx + int(r * 1.1), cy + int(r * 0.2)], start=200, end=340,
                          fill=spec.skin)
        elif style == "bob":
            draw.ellipse([cx - int(r * 1.1), cy - int(r * 1.1),
                          cx + int(r * 1.1), cy + int(r * 0.9)], fill=hair)
            draw.ellipse([cx - int(r * 0.82), cy - int(r * 0.6),
                          cx + int(r * 0.82), cy + int(r * 1.0)], fill=spec.skin)
        elif style == "buzz":
            draw.arc([cx - r, cy - int(r * 1.05), cx + r, cy + int(r * 0.4)],
                     start=180, end=360, fill=hair, width=max(4, r // 6))
        else:  # 'short'
            draw.ellipse([cx - int(r * 1.08), cy - int(r * 1.15),
                          cx + int(r * 1.08), cy + int(r * 0.05)], fill=hair)
            draw.ellipse([cx - int(r * 0.9), cy - int(r * 0.7),
                          cx + int(r * 0.9), cy + int(r * 0.4)], fill=spec.skin)

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
