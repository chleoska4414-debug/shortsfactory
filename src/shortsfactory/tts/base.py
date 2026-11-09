"""Text-to-speech provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple

# Shared narration pacing used by offline providers to size audio to the text.
WORDS_PER_SECOND = 2.8
MIN_DURATION_SEC = 2.0


class TTSProvider(ABC):
    """Base class for all TTS providers."""

    @abstractmethod
    def synthesize(self, text: str, out_wav_path: str) -> Tuple[str, float]:
        """Synthesize ``text`` to an audio file at ``out_wav_path``.

        Returns a tuple of (audio_path, duration_sec).
        """
        raise NotImplementedError


def estimate_duration(text: str) -> float:
    """Estimate narration duration for text, clamped to a minimum."""
    words = len((text or "").split())
    return max(MIN_DURATION_SEC, words / WORDS_PER_SECOND)
