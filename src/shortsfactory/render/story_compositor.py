"""Scene-based micro-drama compositor.

``render_episode`` is the episode analogue of ``render_video``: instead of one background
under a sequence of caption bands, it renders each Scene as its own directed shot - a
per-scene CharacterScene key visual, scene-sized tone/dialog audio, a Korean caption
overlay with micro-drama direction (speaker-name labels for dialog, twist emphasis, an
emphasized CLIFFHANGER card with a '다음 화에 계속' teaser), and short crossfade transitions
between shots. Audio is concatenated like the existing compositor.

Fully offline by default (tone TTS + code-drawn character backgrounds + Pillow captions +
imageio-ffmpeg's bundled ffmpeg). No moviepy TextClip, no system media binaries.
"""

from __future__ import annotations

import os
import tempfile
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..background.character import CharacterScene, _load_label_font
from ..captions.render import render_caption
from ..story.model import KIND_DIALOG, Episode, Scene

CROSSFADE_SEC = 0.4


def _scene_overlay(
    scene: Scene,
    speaker_name: Optional[str],
    accent: Tuple[int, int, int],
    resolution: Tuple[int, int],
    font_path: Optional[str],
) -> Image.Image:
    """Build the full-frame RGBA caption/label overlay for one scene."""
    width, height = resolution
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    if scene.cliffhanger:
        return _cliffhanger_overlay(scene, accent, resolution, font_path)

    # Caption band in the lower third, high-contrast.
    band_h = int(height * 0.34)
    text_color = (255, 255, 255, 255)
    stroke = (0, 0, 0, 255)
    font_size = None
    if scene.emphasis:
        # Twist punch: bigger text in the accent color.
        text_color = (255, 236, 180, 255)
        font_size = int(width * 0.085)

    caption = render_caption(
        scene.text,
        (width, band_h),
        font_path=font_path,
        font_size=font_size,
        text_color=text_color,
        stroke_color=stroke,
    )
    y = height - int(height * 0.12) - band_h
    y = max(0, y)

    # Dim strip behind the caption for legibility.
    draw = ImageDraw.Draw(overlay)
    draw.rectangle([0, y + int(band_h * 0.08), width, y + band_h],
                   fill=(0, 0, 0, 90))
    overlay.alpha_composite(caption, (0, y))

    # Speaker-name label for dialog scenes, styled distinctly from narration.
    if scene.kind == KIND_DIALOG and speaker_name:
        _draw_speaker_label(overlay, speaker_name, accent, resolution, font_path, y)

    return overlay


def _draw_speaker_label(overlay, name, accent, resolution, font_path, caption_y):
    width, height = resolution
    draw = ImageDraw.Draw(overlay)
    font = _label_font(int(width * 0.052), font_path)
    pad_x, pad_y = int(width * 0.03), int(height * 0.008)
    bbox = draw.textbbox((0, 0), name, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    box_w = tw + pad_x * 2
    box_h = th + pad_y * 2
    x = int(width * 0.07)
    y = caption_y - box_h - int(height * 0.015)
    y = max(0, y)
    # Accent tab + dark pill.
    draw.rounded_rectangle([x, y, x + box_w, y + box_h], radius=box_h // 3,
                           fill=(20, 20, 24, 235))
    draw.rounded_rectangle([x, y, x + int(box_w * 0.16), y + box_h],
                           radius=box_h // 3,
                           fill=(accent[0], accent[1], accent[2], 255))
    draw.text((x + pad_x, y + pad_y), name, font=font, fill=(255, 255, 255, 255),
              stroke_width=2, stroke_fill=(0, 0, 0, 255))


def _cliffhanger_overlay(scene, accent, resolution, font_path):
    """Emphasized cliffhanger card: large accent caption + '다음 화에 계속' teaser."""
    width, height = resolution
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Darken the whole frame slightly so the card punches.
    draw.rectangle([0, 0, width, height], fill=(0, 0, 0, 70))

    band_h = int(height * 0.40)
    caption = render_caption(
        scene.text,
        (width, band_h),
        font_path=font_path,
        font_size=int(width * 0.078),
        text_color=(255, 245, 230, 255),
        stroke_color=(0, 0, 0, 255),
    )
    y = int(height * 0.30)
    overlay.alpha_composite(caption, (0, y))

    # Accent rule + teaser tag near the bottom.
    teaser = "다음 화에 계속"
    font = _label_font(int(width * 0.062), font_path)
    bbox = draw.textbbox((0, 0), teaser, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    ty = int(height * 0.80)
    rule_y = ty - int(height * 0.03)
    draw.rectangle([int(width * 0.30), rule_y, int(width * 0.70), rule_y + 6],
                   fill=(accent[0], accent[1], accent[2], 255))
    tx = (width - tw) // 2
    pad = int(width * 0.04)
    draw.rounded_rectangle(
        [tx - pad, ty - int(th * 0.4), tx + tw + pad, ty + th + int(th * 0.4)],
        radius=int(th * 0.7),
        fill=(accent[0], accent[1], accent[2], 235),
    )
    draw.text((tx, ty), teaser, font=font, fill=(255, 255, 255, 255),
              stroke_width=2, stroke_fill=(0, 0, 0, 255))
    return overlay


def _label_font(size, font_path):
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default(size)


def render_episode(
    episode: Episode,
    tts_provider,
    config,
    out_path: str,
    scenes: Optional[List[Scene]] = None,
) -> str:
    """Render ``episode`` (or a subset of ``scenes``) to a 9:16 mp4 at ``out_path``.

    For each scene: synthesize its audio (sized to the Korean text by the tone default),
    build a CharacterScene key visual for the scene duration, overlay the Korean caption +
    speaker label / emphasis / cliffhanger card, and apply a short crossfade so cuts feel
    directed. Per-scene audio is concatenated. Returns the output path.
    """
    from moviepy import (
        AudioFileClip,
        CompositeVideoClip,
        ImageClip,
        concatenate_audioclips,
        concatenate_videoclips,
    )

    resolution = tuple(config.resolution)
    width, height = resolution
    scene_list = list(scenes if scenes is not None else episode.scenes)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    tmp_dir = tempfile.mkdtemp(prefix="shortsfactory_ep_")
    opened_audio = []
    scene_video_clips = []
    audio_clips = []

    try:
        for i, scene in enumerate(scene_list):
            wav_path = os.path.join(tmp_dir, f"scene_{i:03d}.wav")
            _, audio_dur = tts_provider.synthesize(scene.text, wav_path)
            aclip = AudioFileClip(wav_path)
            opened_audio.append(aclip)
            # Scene length is driven by the longer of target vs actual audio so pacing is
            # intentional and audio always fits.
            seg_dur = max(float(scene.target_duration_sec), float(aclip.duration or audio_dur))
            aclip = aclip.with_duration(min(aclip.duration, seg_dur)) if aclip.duration else aclip
            audio_clips.append(aclip)

            staged_id = scene.staged_figure_id()
            character = episode.character(staged_id)
            accent = character.visual.accent if character else (200, 60, 60)
            speaker = episode.character(scene.speaker_id)
            speaker_name = speaker.display_name if speaker else None

            bg = CharacterScene(character=character, scene=scene, seed=scene.index)
            bg_clip = bg.make_clip(seg_dur, resolution).with_duration(seg_dur)

            overlay_img = _scene_overlay(
                scene, speaker_name, accent, resolution, config.font_path
            )
            overlay_arr = np.array(overlay_img)
            cap = (
                ImageClip(overlay_arr, transparent=True)
                .with_duration(seg_dur)
                .with_position((0, 0))
            )

            shot = CompositeVideoClip([bg_clip, cap], size=resolution).with_duration(seg_dur)
            scene_video_clips.append(shot)

        # Crossfade transitions between shots.
        video = _concat_with_crossfade(
            scene_video_clips, concatenate_videoclips, CROSSFADE_SEC
        )

        narration = concatenate_audioclips(audio_clips)
        # Audio total may be shorter than video (crossfades overlap video); pad video to
        # audio or vice versa by clamping to the video duration.
        total = video.duration
        if narration.duration > total:
            narration = narration.with_duration(total)
        video = video.with_audio(narration)

        video.write_videofile(
            out_path,
            fps=config.fps,
            codec="libx264",
            audio_codec="aac",
            logger=None,
        )
        for c in (video, narration):
            try:
                c.close()
            except Exception:
                pass
        return out_path
    finally:
        for aclip in opened_audio:
            try:
                aclip.close()
            except Exception:
                pass
        try:
            for name in os.listdir(tmp_dir):
                try:
                    os.remove(os.path.join(tmp_dir, name))
                except Exception:
                    pass
            os.rmdir(tmp_dir)
        except Exception:
            pass


def _concat_with_crossfade(clips, concatenate_videoclips, fade):
    """Concatenate clips with a short crossfade between consecutive shots.

    Uses moviepy v2 CrossFadeIn/Out effects when available; otherwise falls back to a plain
    concatenation so the render never hard-fails on effect availability.
    """
    if len(clips) <= 1:
        return concatenate_videoclips(clips) if clips else clips[0]
    try:
        from moviepy.video.fx import CrossFadeIn, FadeIn, FadeOut

        faded = []
        for idx, clip in enumerate(clips):
            effects = []
            if idx > 0:
                effects.append(CrossFadeIn(fade))
            else:
                effects.append(FadeIn(min(fade, 0.5)))
            if idx == len(clips) - 1:
                effects.append(FadeOut(min(fade, 0.6)))
            faded.append(clip.with_effects(effects))
        return concatenate_videoclips(faded, padding=-fade, method="compose")
    except Exception:
        return concatenate_videoclips(clips, method="compose")
