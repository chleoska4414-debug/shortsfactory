"""Offline default TTS: a pure stdlib + numpy WAV generator.

ToneTTS does NOT speak real words. It produces a valid, correctly-sized WAV file so the
final video carries a real audio track, without touching pyttsx3, espeak, or the network.
The duration is estimated from the word count so audio length tracks the script.
"""

from __future__ import annotations

import wave
from typing import Tuple

import numpy as np

from .base import TTSProvider, estimate_duration

SAMPLE_RATE = 44100
AMPLITUDE = 0.04  # low-amplitude, unobtrusive tone
BASE_FREQ_HZ = 196.0  # a low G, gentle and non-harsh


class ToneTTS(TTSProvider):
    """Generate a quiet tone bed sized to the text. Fully offline."""

    def __init__(self, sample_rate: int = SAMPLE_RATE, amplitude: float = AMPLITUDE):
        self.sample_rate = sample_rate
        self.amplitude = amplitude

    def synthesize(self, text: str, out_wav_path: str) -> Tuple[str, float]:
        duration_sec = estimate_duration(text)
        n_samples = max(1, int(round(duration_sec * self.sample_rate)))

        t = np.arange(n_samples, dtype=np.float64) / self.sample_rate

        # A soft tone with a gentle fade in/out so it does not click.
        wave_data = np.sin(2.0 * np.pi * BASE_FREQ_HZ * t)
        # Add a quiet harmonic for a slightly warmer bed.
        wave_data += 0.3 * np.sin(2.0 * np.pi * (BASE_FREQ_HZ * 2) * t)
        wave_data *= self.amplitude

        fade_len = min(n_samples, int(0.05 * self.sample_rate))
        if fade_len > 0:
            fade = np.linspace(0.0, 1.0, fade_len)
            wave_data[:fade_len] *= fade
            wave_data[-fade_len:] *= fade[::-1]

        pcm = np.clip(wave_data, -1.0, 1.0)
        pcm16 = (pcm * 32767.0).astype("<i2")

        with wave.open(out_wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm16.tobytes())

        return out_wav_path, duration_sec
