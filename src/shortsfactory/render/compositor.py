"""MoviePy v2 compositor: assemble script + audio + background + captions into an mp4.

The default path is fully offline: tone TTS + gradient background + Pillow captions +
imageio-ffmpeg's bundled ffmpeg. No network, no system media binaries.
"""

from __future__ import annotations

import os
import tempfile
from typing import TYPE_CHECKING

import numpy as np

from ..captions.render import render_segment_overlay

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Config
    from ..script.base import Script


def render_video(script, tts_provider, bg_provider, out_path, config) -> str:
    """Render ``script`` into a 9:16 mp4 at ``out_path``.

    Steps:
      1. Synthesize narration audio per segment via ``tts_provider``.
      2. Build a background clip sized to ``config.resolution`` for the full duration.
      3. For each segment, build a Pillow caption overlay as a timed ImageClip.
      4. Attach the concatenated narration audio.
      5. Write an H.264 mp4 at ``config.fps``.

    Returns the output path.
    """
    from moviepy import (
        AudioFileClip,
        CompositeVideoClip,
        ImageClip,
        concatenate_audioclips,
    )

    resolution = tuple(config.resolution)
    width, height = resolution

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    tmp_dir = tempfile.mkdtemp(prefix="shortsfactory_")
    audio_clips = []
    caption_clips = []
    opened_audio = []  # keep references so we can close them after writing

    try:
        start = 0.0
        for i, segment in enumerate(script.segments):
            wav_path = os.path.join(tmp_dir, f"seg_{i:03d}.wav")
            audio_path, duration = tts_provider.synthesize(segment.text, wav_path)

            aclip = AudioFileClip(audio_path)
            # Prefer the real audio duration; fall back to the estimate.
            seg_duration = float(aclip.duration or duration or segment.est_duration_sec)
            audio_clips.append(aclip)
            opened_audio.append(aclip)

            overlay_img = render_segment_overlay(
                segment.text, resolution, font_path=config.font_path
            )
            overlay_arr = np.array(overlay_img)  # RGBA
            cap = (
                ImageClip(overlay_arr, transparent=True)
                .with_duration(seg_duration)
                .with_start(start)
                .with_position((0, 0))
            )
            caption_clips.append(cap)
            start += seg_duration

        total_duration = max(0.1, start)

        bg_clip = bg_provider.make_clip(total_duration, resolution)
        bg_clip = bg_clip.with_duration(total_duration)

        narration = concatenate_audioclips(audio_clips)

        video = CompositeVideoClip([bg_clip, *caption_clips], size=resolution)
        video = video.with_duration(total_duration).with_audio(narration)

        video.write_videofile(
            out_path,
            fps=config.fps,
            codec="libx264",
            audio_codec="aac",
            logger=None,
        )

        try:
            video.close()
        except Exception:
            pass
        try:
            narration.close()
        except Exception:
            pass

        return out_path
    finally:
        for aclip in opened_audio:
            try:
                aclip.close()
            except Exception:
                pass
        # Best-effort cleanup of temp wavs.
        try:
            for name in os.listdir(tmp_dir):
                try:
                    os.remove(os.path.join(tmp_dir, name))
                except Exception:
                    pass
            os.rmdir(tmp_dir)
        except Exception:
            pass
