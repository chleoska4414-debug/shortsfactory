"""Offline cel-shaded webtoon/anime bust renderer (Pillow only, deterministic).

``render_figure`` draws one character bust as a transparent RGBA layer at the requested
size. It replaces the old stick-figure circles with:

  * 2x supersampled drawing (anti-aliased line art);
  * cel shading: every part gets a base tone, a shadow tone and (for hair/skin) a highlight
    tone built from offset-mask differences, plus a dark outline ring;
  * anime face: shaded face shape with tapered jaw, ears, big eyes (sclera, two-tone iris,
    pupil, two catch-lights, lashes), brows, nose tick, lips, blush, forehead cast shadow;
  * hair with 3 tones, a crown highlight ring and strand lines, shape from ``hair_style``;
  * wardrobe by role: suit + shirt + tie (male lead), blouse + apron (female lead), blazer
    + collar (supporting);
  * expressions (neutral / angry / shock / resigned / worried) incl. a small head tilt.

Everything is a pure function of (VisualSpec, role, expression, eyes_closed, mouth_open).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..story.model import VisualSpec

RGB = Tuple[int, int, int]
Pt = Tuple[float, float]

SS = 2  # supersampling factor

EXPRESSIONS = ("neutral", "angry", "shock", "resigned", "worried")
_TILT = {"neutral": 0.0, "angry": 0.0, "shock": 0.0, "resigned": 4.0, "worried": -3.0}


def _mix(a: RGB, b: RGB, f: float) -> RGB:
    return (
        int(a[0] + (b[0] - a[0]) * f),
        int(a[1] + (b[1] - a[1]) * f),
        int(a[2] + (b[2] - a[2]) * f),
    )


def _spline(pts: List[Pt], n: int = 10) -> List[Pt]:
    """Open Catmull-Rom spline through ``pts``."""
    if len(pts) < 3:
        return list(pts)
    p = [pts[0]] + list(pts) + [pts[-1]]
    out: List[Pt] = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append((
                0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3),
            ))
    out.append(pts[-1])
    return out


@dataclass
class _Part:
    box: Tuple[int, int, int, int]
    mask: Image.Image


class _Painter:
    """A transparent RGBA canvas with cel-shaded part painting."""

    def __init__(self, w: int, h: int, line_col: RGB, line_w: int):
        self.w, self.h = w, h
        self.canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.canvas)
        self.line_col = line_col
        self.line_w = line_w

    # -- shaded part -------------------------------------------------------------------
    def part(
        self,
        fn: Callable[[ImageDraw.ImageDraw], None],
        color: RGB,
        shadow: Optional[RGB] = None,
        hi: Optional[RGB] = None,
        off: int = 0,
        line: Optional[int] = None,
    ) -> Optional[_Part]:
        line = self.line_w if line is None else line
        mask = Image.new("L", (self.w, self.h), 0)
        fn(ImageDraw.Draw(mask))
        bb = mask.getbbox()
        if bb is None:
            return None
        pad = line + off + 6
        box = (max(0, bb[0] - pad), max(0, bb[1] - pad),
               min(self.w, bb[2] + pad), min(self.h, bb[3] + pad))
        m = mask.crop(box)
        if line > 0:
            sigma = max(0.8, line / 1.6)
            dil = m.filter(ImageFilter.GaussianBlur(sigma)).point(lambda v: 255 if v > 12 else 0)
            ring = ImageChops.subtract(dil, m)
            self.canvas.paste(self.line_col, box, ring)
        region = Image.new("RGB", m.size, color)
        if shadow is not None and off:
            sh = ImageChops.subtract(m, ImageChops.offset(m, -off, -off))
            region.paste(shadow, (0, 0), sh)
        if hi is not None and off:
            hm = ImageChops.subtract(m, ImageChops.offset(m, off, off))
            region.paste(hi, (0, 0), hm)
        self.canvas.paste(region, box, m)
        return _Part(box, m)

    # -- detail clipped to a part --------------------------------------------------------
    def detail(
        self,
        part: Optional[_Part],
        fn: Callable[[ImageDraw.ImageDraw], None],
        color: RGB,
        alpha: int = 255,
        blur: float = 0.0,
    ) -> None:
        if part is None:
            return
        tmp = Image.new("L", (self.w, self.h), 0)
        fn(ImageDraw.Draw(tmp))
        t = tmp.crop(part.box)
        if blur:
            t = t.filter(ImageFilter.GaussianBlur(blur))
        t = ImageChops.multiply(t, part.mask)
        if alpha < 255:
            t = t.point(lambda v: v * alpha // 255)
        self.canvas.paste(color, part.box, t)

    # -- direct strokes -------------------------------------------------------------------
    def stroke(self, pts: List[Pt], width: int, color: Optional[RGB] = None, caps: bool = True):
        col = color or self.line_col
        ip = [(int(x), int(y)) for x, y in pts]
        self.d.line(ip, fill=col + (255,), width=width, joint="curve")
        if caps and width > 2:
            rr = width / 2.0
            for x, y in (ip[0], ip[-1]):
                self.d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=col + (255,))

    def tapered(self, pts: List[Pt], w0: float, w1: float, color: Optional[RGB] = None):
        """A stroke whose width goes from ``w0`` to ``w1`` along ``pts``."""
        col = (color or self.line_col) + (255,)
        n = len(pts)
        for i in range(n - 1):
            f = i / max(1, n - 2)
            w = w0 + (w1 - w0) * f
            self.d.line([pts[i], pts[i + 1]], fill=col, width=max(1, int(w)))
            rr = w / 2.0
            self.d.ellipse([pts[i][0] - rr, pts[i][1] - rr, pts[i][0] + rr, pts[i][1] + rr], fill=col)
        rr = w1 / 2.0
        self.d.ellipse([pts[-1][0] - rr, pts[-1][1] - rr, pts[-1][0] + rr, pts[-1][1] + rr], fill=col)


# ----------------------------------------------------------------------------------------
def _face_poly(cx: float, cy: float, r: float, jaw: float) -> List[Pt]:
    pts: List[Pt] = []
    for i in range(0, 72):
        th = 2 * math.pi * i / 72
        s = math.sin(th)
        c = math.cos(th)
        taper = 1.0 - jaw * (max(0.0, s) ** 2.4)
        x = cx + c * r * 0.93 * taper
        y = cy + s * (r * 1.12 if s > 0 else r * 1.0)
        pts.append((x, y))
    return pts


def _ell(d, cx, cy, rx, ry, fill=255):
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=fill)


class _Figure:
    def __init__(self, spec: VisualSpec, role: str, expression: str, w: int, h: int):
        self.spec = spec
        self.role = role
        self.expr = expression if expression in EXPRESSIONS else "neutral"
        self.W, self.H = w * SS, h * SS
        self.fem = (spec.hair_style or "").lower() in ("long", "bob")
        self.cx = int(self.W * spec.anchor_x)
        self.r = int(self.W * 0.16)
        self.cy = int(self.H * 0.385)
        self.line_w = max(4, int(self.r * 0.028))
        base = spec.hair
        self.line_col = _mix(base, (20, 12, 16), 0.55)
        self.skin = spec.skin
        self.skin_sh = _mix(spec.skin, (190, 110, 110), 0.30)
        self.skin_hi = _mix(spec.skin, (255, 250, 240), 0.35)
        self.hair = spec.hair
        self.hair_sh = _mix(spec.hair, (0, 0, 8), 0.45)
        self.hair_hi = _mix(spec.hair, (255, 255, 255), 0.30)
        self.neck_top = self.cy + int(self.r * 0.7)
        self.torso_top = self.cy + int(self.r * 1.18)
        self.pivot = (self.cx, self.torso_top)

    def P(self, **kw) -> _Painter:
        return _Painter(self.W, self.H, self.line_col, self.line_w)

    # -- layers -----------------------------------------------------------------------------
    def back_layer(self) -> Image.Image:
        p = self.P()
        if self.fem:
            cx, cy, r = self.cx, self.cy, self.r
            bottom = cy + (r * 2.9 if (self.spec.hair_style or "").lower() == "long" else r * 1.45)

            def mass(d):
                d.rounded_rectangle([cx - r * 1.22, cy - r * 0.6, cx + r * 1.22, bottom],
                                    radius=int(r * 0.55), fill=255)
                _ell(d, cx, cy - r * 0.05, r * 1.16, r * 1.22)

            p.part(mass, self.hair_sh, off=int(r * 0.05))
        return p.canvas

    def body_layer(self) -> Image.Image:
        p = self.P()
        cx, r, W, H = self.cx, self.r, self.W, self.H
        ttop = self.torso_top
        tb = int(H * 0.93)
        sw = int(W * 0.66)
        acc = self.spec.accent
        acc_sh = _mix(acc, (0, 0, 20), 0.38)
        acc_hi = _mix(acc, (255, 255, 255), 0.22)
        off = int(r * 0.06)
        role = self.role

        # neck (behind clothes collar)
        nw = int(r * 0.62)

        def neck(d):
            d.rounded_rectangle([cx - nw // 2, self.neck_top - r * 0.2, cx + nw // 2, ttop + r * 0.28],
                                radius=nw // 3, fill=255)

        n = p.part(neck, self.skin, self.skin_sh, off=off)
        # shadow under the chin on the neck
        p.detail(n, lambda d: _ell(d, cx, self.neck_top - r * 0.05, r * 0.6, r * 0.42),
                 self.skin_sh, alpha=210, blur=r * 0.05)

        if role == "female_lead":
            sw = int(sw * 0.9)

        def torso(d):
            # sloped shoulders (spline) down to a straight body
            left = _spline([(cx - nw * 0.9, ttop - r * 0.25), (cx - sw * 0.2, ttop - r * 0.02),
                            (cx - sw * 0.42, ttop + r * 0.22), (cx - sw * 0.5, ttop + r * 0.75),
                            (cx - sw * 0.5, ttop + r * 1.6)], 10)
            right = [(2 * cx - x, y) for x, y in left]
            d.polygon(left + [(cx - sw * 0.5, tb + r), (cx + sw * 0.5, tb + r)] + right[::-1], fill=255)

        if role == "female_lead":
            blouse = (246, 238, 228)
            p.part(torso, blouse, _mix(blouse, (150, 120, 120), 0.30), off=off)
            # neckline
            p.part(lambda d: d.polygon([(cx - nw * 0.95, ttop - r * 0.5), (cx + nw * 0.95, ttop - r * 0.5),
                                        (cx + nw * 0.95, ttop + r * 0.05), (cx, ttop + r * 0.62),
                                        (cx - nw * 0.95, ttop + r * 0.05)], fill=255),
                   self.skin, self.skin_sh, off=off // 2, line=0)
            p.stroke([(cx - nw * 0.95, ttop + r * 0.05), (cx, ttop + r * 0.62), (cx + nw * 0.95, ttop + r * 0.05)],
                     self.line_w)
            # apron bib + straps
            bib_top = ttop + r * 0.78
            ap = p.part(lambda d: d.polygon([(cx - sw * 0.27, bib_top), (cx + sw * 0.27, bib_top),
                                             (cx + sw * 0.34, tb + r), (cx - sw * 0.34, tb + r)], fill=255),
                        acc, acc_sh, acc_hi, off=off)
            for sgn in (-1, 1):
                p.part(lambda d, s=sgn: d.polygon([(cx + s * sw * 0.22, bib_top + 6), (cx + s * sw * 0.30, bib_top + 6),
                                                   (cx + s * nw * 1.05, ttop + r * 0.12), (cx + s * nw * 0.6, ttop + r * 0.06)],
                                                  fill=255), acc, acc_sh, off=off // 2)
            # apron pocket line + fold shading
            p.stroke([(cx - sw * 0.2, bib_top + r * 1.3), (cx + sw * 0.2, bib_top + r * 1.3)],
                     self.line_w, caps=True)
            p.detail(ap, lambda d: d.polygon([(cx + sw * 0.05, bib_top), (cx + sw * 0.34, bib_top),
                                              (cx + sw * 0.34, tb + r), (cx + sw * 0.12, tb + r)], fill=255),
                     acc_sh, alpha=110)
        elif role == "male_lead":
            t = p.part(torso, acc, acc_sh, acc_hi, off=off)
            # white shirt V
            shirt = (244, 244, 248)
            p.part(lambda d: d.polygon([(cx - nw * 1.05, ttop - 4), (cx + nw * 1.05, ttop - 4),
                                        (cx + r * 0.1, ttop + r * 1.9), (cx - r * 0.1, ttop + r * 1.9)], fill=255),
                   shirt, _mix(shirt, (110, 120, 160), 0.30), off=off // 2)
            # tie
            tie = (150, 36, 52)
            p.part(lambda d: d.polygon([(cx - r * 0.12, ttop + r * 0.1), (cx + r * 0.12, ttop + r * 0.1),
                                        (cx + r * 0.2, ttop + r * 1.0), (cx, ttop + r * 1.95),
                                        (cx - r * 0.2, ttop + r * 1.0)], fill=255),
                   tie, _mix(tie, (0, 0, 0), 0.4), off=off // 2)
            # lapels
            for sgn in (-1, 1):
                p.part(lambda d, s=sgn: d.polygon([(cx + s * nw * 1.0, ttop - 2), (cx + s * nw * 1.7, ttop + r * 0.15),
                                                   (cx + s * r * 0.28, ttop + r * 1.9), (cx + s * r * 0.12, ttop + r * 1.9)],
                                                  fill=255), acc_hi, acc_sh, off=off // 2)
        else:  # blazer + collar
            p.part(torso, acc, acc_sh, acc_hi, off=off)
            p.part(lambda d: d.polygon([(cx - nw * 1.1, ttop - 4), (cx + nw * 1.1, ttop - 4),
                                        (cx, ttop + r * 1.1)], fill=255), (246, 246, 250),
                   _mix((246, 246, 250), (120, 120, 150), 0.3), off=off // 2)
            for sgn in (-1, 1):
                p.part(lambda d, s=sgn: d.polygon([(cx + s * nw * 1.0, ttop - 2), (cx + s * nw * 1.8, ttop + r * 0.2),
                                                   (cx + s * r * 0.1, ttop + r * 1.15)], fill=255),
                       acc_hi, acc_sh, off=off // 2)
        return p.canvas

    def head_layer(self, eyes_closed: bool, mouth_open: bool) -> Image.Image:
        p = self.P()
        cx, cy, r = self.cx, self.cy, self.r
        off = int(r * 0.06)
        fem = self.fem
        expr = self.expr
        jaw = 0.34 if fem else 0.26

        # ears
        for sgn in (-1, 1):
            ear = p.part(lambda d, s=sgn: _ell(d, cx + s * r * 0.92, cy + r * 0.2, r * 0.13, r * 0.2),
                         self.skin, self.skin_sh, off=off // 2)
            p.detail(ear, lambda d, s=sgn: _ell(d, cx + s * r * 0.93, cy + r * 0.22, r * 0.06, r * 0.1),
                     self.skin_sh, alpha=200)

        # face
        face = p.part(lambda d: d.polygon(_face_poly(cx, cy, r, jaw), fill=255),
                      self.skin, self.skin_sh, self.skin_hi, off=off)
        # forehead cast shadow from the fringe
        p.detail(face, lambda d: _ell(d, cx, cy - r * 0.78, r * 1.05, r * 0.5), self.skin_sh, alpha=120, blur=r * 0.06)
        # soft cheek blush
        blush = (236, 120, 130)
        ba = 110 if fem else 45
        for sgn in (-1, 1):
            p.detail(face, lambda d, s=sgn: _ell(d, cx + s * r * 0.56, cy + r * 0.5, r * 0.2, r * 0.11),
                     blush, alpha=ba, blur=r * 0.05)
        # jaw side shading
        p.detail(face, lambda d: (_ell(d, cx - r * 1.05, cy + r * 0.7, r * 0.35, r * 0.9)), self.skin_sh, alpha=60, blur=r * 0.1)

        # nose: a small shadow tick
        p.stroke([(cx - r * 0.025, cy + r * 0.38), (cx + r * 0.03, cy + r * 0.47)],
                 max(3, int(r * 0.02)), self.skin_sh, caps=True)
        p.stroke([(cx + r * 0.03, cy + r * 0.47), (cx - r * 0.02, cy + r * 0.485)],
                 max(3, int(r * 0.02)), _mix(self.skin_sh, self.line_col, 0.35), caps=True)

        self._eyes(p, eyes_closed)
        self._brows(p)
        self._mouth(p, mouth_open)
        self._front_hair(p)
        return p.canvas

    # -- facial features ---------------------------------------------------------------------
    def _eyes(self, p: _Painter, closed: bool) -> None:
        cx, cy, r = self.cx, self.cy, self.r
        fem = self.fem
        expr = self.expr
        ew = r * (0.19 if fem else 0.165)
        eh = r * (0.215 if fem else 0.16)
        if expr == "shock":
            eh *= 1.18
            ew *= 1.05
        ey = cy + r * 0.2
        iris_dark = _mix(self.hair, (70, 40, 40), 0.35)
        iris_light = _mix(self.hair, (190, 130, 90), 0.55) if fem else _mix(self.hair, (120, 130, 170), 0.5)
        lw = max(4, int(r * (0.05 if fem else 0.04)))
        for sgn in (-1, 1):
            ex = cx + sgn * r * 0.42
            if closed:
                pts = [(ex + sgn * ew * 1.0 * k, ey + eh * 0.15 * (1 - k * k) * 1.4 + 0)
                       for k in (-1, -0.5, 0, 0.5, 1)]
                arc = [(ex - ew, ey - eh * 0.1), (ex - ew * 0.5, ey + eh * 0.4), (ex, ey + eh * 0.5),
                       (ex + ew * 0.5, ey + eh * 0.4), (ex + ew, ey - eh * 0.1)]
                p.stroke(_spline(arc, 6), lw)
                if fem:
                    p.stroke([(ex + sgn * ew, ey - eh * 0.1), (ex + sgn * (ew + r * 0.07), ey - eh * 0.28)], lw)
                continue
            lid_cut = 0.0
            if expr == "resigned":
                lid_cut = 0.42
            elif expr == "angry":
                lid_cut = 0.18
            sclera = (252, 250, 248)
            sc = p.part(lambda d: _ell(d, ex, ey, ew, eh), sclera, line=0)
            # upper lid shadow on the eyeball
            p.detail(sc, lambda d: _ell(d, ex, ey - eh * 0.75, ew * 1.3, eh * 0.7), (150, 120, 130), alpha=130, blur=r * 0.01)
            ir = (0.62 if expr == "shock" else 0.82)
            irx, iry = ew * ir, eh * min(1.0, ir * 1.15)
            iy = ey + eh * 0.04
            p.detail(sc, lambda d: _ell(d, ex, iy, irx, iry), iris_dark)
            # lighter lower half of the iris (anime gradient)
            p.detail(sc, lambda d: (_ell(d, ex, iy + iry * 0.38, irx * 0.85, iry * 0.55)), iris_light, alpha=190, blur=r * 0.006)
            # pupil
            p.detail(sc, lambda d: _ell(d, ex, iy, irx * 0.46, iry * 0.5), (14, 10, 16))
            # catch-lights
            hx, hy = ex - irx * 0.34, iy - iry * 0.36
            hr = irx * 0.30
            p.d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=(255, 255, 255, 255))
            h2 = irx * 0.14
            p.d.ellipse([ex + irx * 0.38 - h2, iy + iry * 0.42 - h2, ex + irx * 0.38 + h2, iy + iry * 0.42 + h2],
                        fill=(255, 255, 255, 235))
            # drooping lid for the resigned / angry look: skin covers the top of the eye
            top = ey - eh
            if lid_cut:
                cut_y = top + eh * 2 * lid_cut
                tilt = (-eh * 0.35 * sgn * -1) if expr == "angry" else 0
                # angry: inner side lower. inner side is toward the center (-sgn).
                inner_y = cut_y + (eh * 0.45 if expr == "angry" else 0)
                outer_y = cut_y
                poly = [(ex - ew * 1.4, top - eh * 0.6), (ex + ew * 1.4, top - eh * 0.6)]
                if sgn == -1:   # left eye: inner = right side
                    poly += [(ex + ew * 1.15, inner_y), (ex - ew * 1.15, outer_y)]
                else:
                    poly += [(ex + ew * 1.15, outer_y), (ex - ew * 1.15, inner_y)]
                lid = Image.new("L", (self.W, self.H), 0)
                ImageDraw.Draw(lid).polygon(poly, fill=255)
                lm = ImageChops.multiply(lid.crop(sc.box), sc.mask)
                p.canvas.paste(self.skin, sc.box, lm)
                lash_pts = ([(ex - ew * 1.1, outer_y if sgn == 1 else outer_y), (ex, (cut_y + inner_y) / 2), (ex + ew * 1.1, inner_y if sgn == -1 else inner_y)])
                if sgn == -1:
                    lash_pts = [(ex - ew * 1.1, outer_y), (ex, (outer_y + inner_y) / 2), (ex + ew * 1.1, inner_y)]
                else:
                    lash_pts = [(ex - ew * 1.1, inner_y), (ex, (outer_y + inner_y) / 2), (ex + ew * 1.1, outer_y)]
                p.stroke(lash_pts, lw)
            else:
                # thick upper lash arc + outer wing
                arc = [(ex - ew * 1.05, ey + eh * 0.15), (ex - ew * 0.6, ey - eh * 0.82), (ex, ey - eh * 1.08),
                       (ex + ew * 0.6, ey - eh * 0.82), (ex + ew * 1.05, ey + eh * 0.15)]
                p.stroke(_spline(arc, 6), lw)
                if fem:
                    ox = ex + sgn * ew * 1.05
                    p.stroke([(ox, ey + eh * 0.05), (ox + sgn * r * 0.09, ey - eh * 0.38)], lw)
                    p.stroke([(ox, ey - eh * 0.05), (ox + sgn * r * 0.05, ey - eh * 0.62)], max(3, lw // 2))
            # faint lower lid
            low = [(ex - ew * 0.8, ey + eh * 0.95), (ex, ey + eh * 1.12), (ex + ew * 0.8, ey + eh * 0.95)]
            p.stroke(_spline(low, 5), max(2, lw // 3), _mix(self.skin_sh, self.line_col, 0.4), caps=False)

    def _brows(self, p: _Painter) -> None:
        cx, cy, r = self.cx, self.cy, self.r
        expr = self.expr
        by = cy - r * 0.2
        # (outer_dy, mid_dy, inner_dy) in units of r (negative = higher)
        shape = {
            "neutral": (-0.02, -0.06, 0.0),
            "angry": (-0.10, -0.02, 0.10),
            "shock": (-0.22, -0.30, -0.22),
            "resigned": (0.03, 0.0, -0.04),
            "worried": (0.04, -0.04, -0.14),
        }[expr]
        w0 = r * (0.05 if self.fem else 0.075)
        for sgn in (-1, 1):
            ex = cx + sgn * r * 0.42
            pts = [
                (ex + sgn * r * 0.22, by + shape[0] * r),
                (ex, by + shape[1] * r),
                (ex - sgn * r * 0.2, by + shape[2] * r),
            ]
            pts = _spline(pts, 8)
            col = _mix(self.hair, (0, 0, 0), 0.2)
            # thicker at the inner end
            p.tapered(pts[::-1], w0 * 1.15, w0 * 0.45, col)

    def _mouth(self, p: _Painter, open_: bool) -> None:
        cx, cy, r = self.cx, self.cy, self.r
        expr = self.expr
        my = cy + r * 0.66
        mw = r * 0.2
        lip = (214, 96, 110) if self.fem else _mix(self.skin, (170, 80, 80), 0.45)
        lw = max(3, int(r * 0.024))
        if open_ or expr == "shock":
            hh = r * (0.2 if expr == "shock" else 0.15)
            ww = r * (0.14 if expr == "shock" else 0.2)
            if expr == "shock" and not open_:
                hh *= 0.8
            m = p.part(lambda d: _ell(d, cx, my + hh * 0.3, ww, hh), (92, 28, 40), line=self.line_w)
            p.detail(m, lambda d: _ell(d, cx, my + hh * 0.9, ww * 0.75, hh * 0.55), (214, 96, 110), alpha=255)
            p.detail(m, lambda d: d.rectangle([cx - ww, my - hh * 0.8, cx + ww, my - hh * 0.2], fill=255), (250, 248, 246))
            return
        if expr == "angry":
            pts = [(cx - mw, my + r * 0.03), (cx, my - r * 0.02), (cx + mw, my + r * 0.03)]
        elif expr == "resigned":
            pts = [(cx - mw * 0.8, my + r * 0.015), (cx, my + r * 0.0), (cx + mw * 0.8, my + r * 0.045)]
        elif expr == "worried":
            pts = [(cx - mw * 0.8, my + r * 0.04), (cx, my - r * 0.01), (cx + mw * 0.8, my + r * 0.04)]
        else:
            pts = [(cx - mw, my - r * 0.005), (cx, my + r * 0.04), (cx + mw, my - r * 0.005)]
        sp = _spline(pts, 8)
        p.stroke(sp, lw + 2, _mix(self.line_col, (120, 40, 50), 0.4))
        if self.fem and expr != "angry":
            # small glossy lower lip
            low = [(cx - mw * 0.6, my + r * 0.045), (cx, my + r * 0.085), (cx + mw * 0.6, my + r * 0.045)]
            p.stroke(_spline(low, 6), lw + 1, lip, caps=True)

    # -- hair ----------------------------------------------------------------------------------
    def _crown(self, rx: float, ry: float, y0: float, a0=180, a1=360, n=36) -> List[Pt]:
        cx, cy, r = self.cx, self.cy, self.r
        pts = []
        for i in range(n + 1):
            a = math.radians(a0 + (a1 - a0) * i / n)
            pts.append((cx + math.cos(a) * rx * r, cy + y0 * r + math.sin(a) * ry * r))
        return pts

    def _front_hair(self, p: _Painter) -> None:
        cx, cy, r = self.cx, self.cy, self.r
        style = (self.spec.hair_style or "short").lower()
        off = int(r * 0.07)

        def Q(x, y):
            return (cx + x * r, cy + y * r)

        # fringe silhouette (screen-left → right) built from crown arc + jagged lock tips
        crown = self._crown(1.07, 1.2, -0.02)  # left temple -> over the top -> right temple
        if style == "swept":
            lower = [Q(1.0, 0.12), Q(0.95, 0.34), Q(0.84, 0.0), Q(0.82, -0.22), Q(0.62, -0.1), Q(0.46, -0.34),
                     Q(0.3, -0.12), Q(0.02, -0.5), Q(-0.12, -0.2), Q(-0.4, -0.45), Q(-0.56, -0.18),
                     Q(-0.82, -0.2), Q(-0.86, 0.1), Q(-0.9, 0.34), Q(-1.0, 0.12)]
        elif style == "buzz":
            lower = [Q(0.98, 0.0), Q(0.7, -0.5), Q(0.0, -0.62), Q(-0.7, -0.5), Q(-0.98, 0.0)]
        elif style == "short":
            lower = [Q(1.0, 0.1), Q(0.9, 0.3), Q(0.78, -0.1), Q(0.55, -0.35), Q(0.3, -0.2), Q(0.0, -0.45),
                     Q(-0.3, -0.2), Q(-0.55, -0.35), Q(-0.78, -0.1), Q(-0.9, 0.3), Q(-1.0, 0.1)]
        else:  # long / bob: center-parted jagged fringe
            lower = [Q(1.0, 0.1), Q(0.9, 0.0), Q(0.78, -0.3), Q(0.68, 0.06), Q(0.5, -0.36), Q(0.36, 0.08),
                     Q(0.22, -0.4), Q(0.08, 0.0), Q(0.0, -0.5), Q(-0.08, 0.0), Q(-0.22, -0.4), Q(-0.36, 0.08),
                     Q(-0.5, -0.36), Q(-0.68, 0.06), Q(-0.78, -0.3), Q(-0.9, 0.0), Q(-1.0, 0.1)]

        def fringe(d):
            d.polygon(crown + lower, fill=255)

        hairp = p.part(fringe, self.hair, self.hair_sh, self.hair_hi, off=off)

        # side locks for long / bob hair (fall in front of the shoulders)
        if self.fem:
            bottom = 2.55 if style == "long" else 1.35
            inward = 0.58 if style == "long" else 0.62
            for sgn in (-1, 1):
                lock = _spline([Q(sgn * 1.0, -0.05), Q(sgn * 1.2, bottom * 0.25), Q(sgn * 1.3, bottom * 0.6),
                                Q(sgn * 1.22, bottom * 0.92)], 8)
                lock += [Q(sgn * 1.0, bottom + 0.18)]
                lock += _spline([Q(sgn * 0.9, bottom * 0.8), Q(sgn * 0.84, bottom * 0.5), Q(sgn * 0.8, 0.45),
                                 Q(sgn * 0.82, 0.05)], 8)
                lp = p.part(lambda d, L=lock: d.polygon(L, fill=255), self.hair, self.hair_sh, self.hair_hi, off=off)
                p.detail(lp, lambda d, s=sgn: self._strands(d, s, bottom), self.hair_sh, alpha=170)

        # crown highlight ring ("angel ring") + strand lines on the fringe
        def ring(d):
            for k in range(3):
                pts = self._crown(0.82 - k * 0.02, 0.86 - k * 0.02, -0.02, 200, 340, 24)
                d.line([(x, y + r * 0.06 * k) for x, y in pts], fill=255, width=int(r * 0.07), joint="curve")
        p.detail(hairp, ring, self.hair_hi, alpha=150, blur=r * 0.012)

        def lines(d):
            n = 7
            for i in range(n):
                f = (i + 0.5) / n
                x0 = cx + (f - 0.5) * r * 1.5
                pts = [(x0, cy - 1.18 * r + abs(f - 0.5) * r * 0.4),
                       (x0 + (f - 0.5) * r * 0.6, cy - 0.7 * r),
                       (x0 + (f - 0.5) * r * 0.9, cy - 0.25 * r)]
                d.line(_spline(pts, 8), fill=255, width=max(2, int(r * 0.016)))
        p.detail(hairp, lines, self.hair_sh, alpha=190)

        # a couple of loose hair strands falling on the forehead (fine anime detail)
        sk = _mix(self.hair, (0, 0, 0), 0.1)
        for sgn, x in ((-1, -0.2), (1, 0.28)):
            pts = [Q(x, -0.45), Q(x + sgn * 0.04, -0.2), Q(x - sgn * 0.02, 0.1)]
            p.tapered(_spline(pts, 8), r * 0.035, r * 0.01, sk)

    def _strands(self, d, sgn: int, bottom: float) -> None:
        cx, cy, r = self.cx, self.cy, self.r
        for i in range(4):
            x = sgn * (0.86 + 0.07 * i)
            pts = [(cx + x * r, cy + 0.2 * r), (cx + (x + sgn * 0.03) * r, cy + bottom * 0.5 * r),
                   (cx + (x - sgn * 0.02) * r, cy + bottom * 0.95 * r)]
            d.line(_spline(pts, 8), fill=255, width=max(2, int(r * 0.014)))


_body_cache: Dict[tuple, Image.Image] = {}


def render_figure(
    spec: VisualSpec,
    role: str,
    width: int,
    height: int,
    expression: str = "neutral",
    eyes_closed: bool = False,
    mouth_open: bool = False,
    cache: Optional[dict] = None,
) -> Image.Image:
    """Render the cel-shaded bust as an RGBA image of exactly (width, height)."""
    fig = _Figure(spec, role, expression, width, height)
    store = cache if cache is not None else _body_cache
    key = ("static", spec.accent, spec.hair, spec.skin, spec.hair_style, spec.anchor_x, role, width, height)
    static = store.get(key)
    if static is None:
        back = fig.back_layer()
        body = fig.body_layer()
        static = (back, body)
        store[key] = static
    back, body = static

    head = fig.head_layer(eyes_closed, mouth_open)
    tilt = _TILT.get(fig.expr, 0.0)
    # Head + back hair rotate together around the neck base.
    if tilt:
        piv = fig.pivot
        back_r = back.rotate(tilt, resample=Image.BICUBIC, center=piv)
        head = head.rotate(tilt, resample=Image.BICUBIC, center=piv)
    else:
        back_r = back

    # Order: back hair, body, (neck is in body), head. Head covers the neck top.
    out = Image.new("RGBA", back.size, (0, 0, 0, 0))
    out.alpha_composite(back_r)
    out.alpha_composite(body)
    out.alpha_composite(head)

    # Outer silhouette line so the whole figure reads as one inked illustration.
    a = out.getchannel("A")
    sigma = max(1.0, fig.line_w * 0.9 / 1.6)
    dil = a.filter(ImageFilter.GaussianBlur(sigma)).point(lambda v: 255 if v > 12 else 0)
    ring = ImageChops.subtract(dil, a)
    under = Image.new("RGBA", out.size, (0, 0, 0, 0))
    under.paste(fig.line_col, (0, 0), ring)
    under.alpha_composite(out)
    return under.resize((width, height), Image.LANCZOS)
