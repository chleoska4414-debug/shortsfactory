"""Tests for the offline tone TTS provider.

These assert the WAV is real and readable via stdlib wave, that its duration roughly
matches the word-count estimate, and that generation uses only stdlib + numpy (no
pyttsx3, no espeak, no network).
"""

from __future__ import annotations

import sys
import wave

from shortsfactory.tts import ToneTTS, get_tts_provider
from shortsfactory.tts.base import WORDS_PER_SECOND, estimate_duration


def test_tone_writes_readable_wav(tmp_path):
    out = tmp_path / "narration.wav"
    text = "This is a short offline narration used to size the generated tone audio."
    provider = ToneTTS()
    audio_path, duration = provider.synthesize(text, str(out))

    assert audio_path == str(out)
    assert out.exists() and out.stat().st_size > 0

    with wave.open(str(out), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        actual = frames / float(rate)

    assert actual > 0
    # Duration should track the word-count estimate closely.
    expected = estimate_duration(text)
    assert abs(actual - expected) < 0.2
    assert abs(duration - expected) < 0.2


def test_tone_duration_scales_with_words(tmp_path):
    provider = ToneTTS()
    short = "one two three"
    long = " ".join(["word"] * 60)
    _, short_dur = provider.synthesize(short, str(tmp_path / "s.wav"))
    _, long_dur = provider.synthesize(long, str(tmp_path / "l.wav"))
    assert long_dur > short_dur
    assert long_dur >= 60 / WORDS_PER_SECOND - 0.1


def test_tone_uses_no_network_or_espeak(tmp_path):
    # pyttsx3 (espeak) must not be imported as a side effect of tone synthesis.
    provider = get_tts_provider("tone")
    provider.synthesize("hello world", str(tmp_path / "x.wav"))
    assert "pyttsx3" not in sys.modules
    assert "edge_tts" not in sys.modules
    assert "gtts" not in sys.modules
