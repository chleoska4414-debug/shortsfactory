"""Quality checks for the cel-shaded code-drawn character figure."""

import numpy as np

from shortsfactory.background.character import CharacterScene
from shortsfactory.background.figure import EXPRESSIONS, render_figure
from shortsfactory.story.episodes import get_episode

W, H = 540, 960  # small size keeps the tests fast


def _fig(role_name, **kw):
    ep = get_episode("ep01")
    ch = next(c for c in ep.characters if c.role == role_name)
    return render_figure(ch.visual, ch.role, W, H, **kw), ch


def _palette_size(img):
    a = np.asarray(img)
    opaque = a[a[:, :, 3] > 250][:, :3]
    # quantize to 4 bits per channel so AA noise does not inflate the count
    q = (opaque >> 4).astype(np.int32)
    return len(np.unique(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]))


def test_figure_is_rgba_with_expected_size_and_transparency():
    img, _ = _fig("male_lead")
    assert img.mode == "RGBA" and img.size == (W, H)
    alpha = np.asarray(img)[:, :, 3]
    assert alpha[0, 0] == 0 and alpha.max() == 255


def test_figure_is_shaded_not_flat_blocks():
    for role in ("male_lead", "female_lead"):
        img, _ = _fig(role)
        # A flat stick-figure has a handful of colours; a shaded cel figure has many tones.
        assert _palette_size(img) >= 40, role


def test_face_region_has_line_art_and_detail():
    img, ch = _fig("female_lead")
    a = np.asarray(img).astype(np.int32)
    cx, cy = int(W * 0.5), int(H * 0.385)
    r = int(W * 0.16)
    face = a[cy - r // 2: cy + r // 2, cx - r: cx + r, :3]
    lum = face.mean(axis=2)
    assert lum.std() > 25.0                  # eyes/brows/lashes create real contrast
    assert (lum < 70).sum() > 150            # dark ink / pupils exist
    assert (lum > 235).sum() > 40            # catch-lights / sclera highlights exist


def test_male_and_female_are_clearly_different():
    m, _ = _fig("male_lead")
    f, _ = _fig("female_lead")
    assert not np.array_equal(np.asarray(m), np.asarray(f))
    # Long hair makes the female silhouette wider at the shoulder-line of the head.
    row = int(H * 0.50)
    wm = (np.asarray(m)[row, :, 3] > 0).sum()
    wf = (np.asarray(f)[row, :, 3] > 0).sum()
    assert wm != wf


def test_deterministic():
    a, _ = _fig("female_lead", expression="angry")
    b, _ = _fig("female_lead", expression="angry")
    assert np.array_equal(np.asarray(a), np.asarray(b))


def test_expressions_and_blink_mouth_variants_differ():
    base, _ = _fig("male_lead")
    base = np.asarray(base)
    for e in EXPRESSIONS:
        if e == "neutral":
            continue
        img, _ = _fig("male_lead", expression=e)
        assert not np.array_equal(np.asarray(img), base), e
    blink, _ = _fig("male_lead", eyes_closed=True)
    mouth, _ = _fig("male_lead", mouth_open=True)
    assert not np.array_equal(np.asarray(blink), base)
    assert not np.array_equal(np.asarray(mouth), base)


def test_scene_expression_is_derived_from_flags():
    ep = get_episode("ep01")
    cs = {i: CharacterScene(ep.character(s.staged_figure_id() or s.speaker_id), s, seed=i)
          for i, s in enumerate(ep.scenes)}
    assert cs[0]._expression() == "worried"      # rainy hook
    assert cs[5]._expression() == "angry"        # emphasized dialog
    assert cs[9]._expression() == "resigned"     # emphasized narration
    assert cs[10]._expression() == "angry"       # cliffhanger flash line
    assert cs[11]._expression() == "shock"       # cliffhanger card
    assert cs[4]._expression() == "neutral"


def test_raised_hand_is_role_specific_and_cache_safe():
    # At shoulder height the hand adds visible skin outside the relaxed pose.
    row = int(H * 0.385 + W * 0.16 * 1.3)
    hand = (slice(row, row + int(W * 0.035)), slice(0, int(W * 0.21)), slice(0, 3))
    for role in ("male_lead", "female_lead", "supporting"):
        cache = {}
        neutral, ch = _fig(role, cache=cache)
        shock, _ = _fig(role, expression="shock", cache=cache)
        assert np.array_equal(shock, _fig(role, expression="shock", cache={})[0])
        blink, _ = _fig(role, expression="shock", eyes_closed=True, cache=cache)
        assert np.array_equal(np.asarray(shock)[row:], np.asarray(blink)[row:])
        assert np.array_equal(neutral, _fig(role, cache=cache)[0])
        if role == "supporting":
            assert len(cache) == 1
            assert np.array_equal(np.asarray(neutral)[row:], np.asarray(shock)[row:])
        else:
            assert len(cache) == 2
            assert not (np.asarray(neutral)[hand] == ch.visual.skin).all(axis=-1).any()
            assert (np.asarray(shock)[hand] == ch.visual.skin).all(axis=-1).sum() > 50


def test_sleeve_folds_create_ink_and_shadow_inside_jacket():
    from shortsfactory.background.figure import _mix

    img, ch = _fig("supporting")
    r = W * 0.16
    top = H * 0.385 + 1.18 * r
    pixels = np.asarray(img)[int(top + 0.9 * r):int(top + 1.65 * r),
                             int(W * 0.62):int(W * 0.81), :3]
    base = ch.visual.accent
    shadow = _mix(base, (0, 0, 20), 0.38)
    for tone in (base, shadow):
        assert (pixels == tone).all(axis=-1).sum() > 100
    assert (pixels.mean(axis=-1) < np.mean(shadow) - 5).sum() > 20


def test_front_locks_taper_toward_tips_for_long_and_bob():
    from shortsfactory.background.figure import _Figure

    for role, tip in (("female_lead", 2.72), ("supporting", 1.55)):
        _, ch = _fig(role)
        fig = _Figure(ch.visual, role, "neutral", W, H)
        painter = fig.P()
        fig._front_hair(painter)
        alpha = np.asarray(painter.canvas)[:, fig.cx:, 3]
        middle = (alpha[int(fig.cy + 0.64 * fig.r)] == 255).sum()
        end = (alpha[int(fig.cy + (tip - 0.08) * fig.r)] == 255).sum()
        assert 0 < end < middle * 0.55, ch.visual.hair_style
