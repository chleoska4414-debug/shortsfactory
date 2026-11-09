"""Optional network TTS using gTTS (Google Translate TTS).

Not exercised by the offline test suite. Lazily imports gTTS and performs a network call;
raises a clear, actionable RuntimeError if the dependency is missing or the call fails.
"""

from __future__ import annotations

from typing import Tuple

from .base import TTSProvider


class GTTSProvider(TTSProvider):
    """Synthesize speech with gTTS. Requires the extra and outbound network."""

    def __init__(self, lang: str = "en"):
        self.lang = lang or "en"

    def synthesize(self, text: str, out_wav_path: str) -> Tuple[str, float]:
        try:
            from gtts import gTTS  # lazy import
        except Exception as exc:  # pragma: no cover - network provider
            raise RuntimeError(
                "The 'gtts' TTS provider requires the gTTS package. "
                "Install it with: pip install 'shortsfactory[providers]'  (or: pip install gTTS). "
                "Note this provider also needs outbound internet access to Google servers."
            ) from exc

        if out_wav_path.lower().endswith(".wav"):
            out_path = out_wav_path[:-4] + ".mp3"
        else:
            out_path = out_wav_path

        try:
            tts = gTTS(text=text, lang=self.lang)
            tts.save(out_path)
        except Exception as exc:  # pragma: no cover - network provider
            raise RuntimeError(
                "gTTS synthesis failed. This provider needs outbound internet access to "
                "Google servers, which is not available in offline environments. "
                "Use --provider-tts tone for a fully offline run. "
                f"Underlying error: {exc}"
            ) from exc

        duration = self._probe_duration(out_path)
        return out_path, duration

    @staticmethod
    def _probe_duration(path: str) -> float:  # pragma: no cover - network provider
        try:
            from moviepy import AudioFileClip

            clip = AudioFileClip(path)
            dur = float(clip.duration)
            clip.close()
            return dur
        except Exception:
            return 0.0
