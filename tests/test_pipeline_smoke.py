"""End-to-end offline smoke test: the core proof of the MVP.

Runs the full pipeline (topic -> script -> tone TTS -> gradient bg -> Pillow captions ->
mp4) with a small card count so the render is fast, then probes the output with moviepy.
MUST pass with no network and no system ffmpeg/espeak/imagemagick.
"""

from __future__ import annotations

import os

from shortsfactory import pipeline


def test_pipeline_generates_vertical_mp4_with_audio(tmp_path):
    out_path = str(tmp_path / "space.mp4")

    result = pipeline.generate(
        topic="space",
        out_path=out_path,
        tts_name="tone",
        bg_name="gradient",
        n_cards=3,
    )

    assert result == out_path
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 0

    from moviepy import VideoFileClip

    clip = VideoFileClip(out_path)
    try:
        assert tuple(clip.size) == (1080, 1920)
        assert clip.audio is not None
        assert clip.duration > 0
    finally:
        clip.close()
