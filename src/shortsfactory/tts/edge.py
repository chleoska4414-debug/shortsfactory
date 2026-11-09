"""Optional network TTS using edge-tts (Microsoft Edge online voices).

This provider is NOT exercised by the offline test suite. It lazily imports edge-tts and
performs a network call; if the dependency is missing or the network is unavailable it
raises a clear, actionable RuntimeError instead of leaking a deep internal traceback.
"""

from __future__ import annotations

import asyncio
import wave
from typing import Tuple

from .base import TTSProvider

DEFAULT_VOICE = "en-US-AriaNeural"


class EdgeTTS(TTSProvider):
    """Synthesize speech with edge-tts. Requires the extra and outbound network."""

    def __init__(self, voice: str = DEFAULT_VOICE):
        self.voice = voice or DEFAULT_VOICE

    def synthesize(self, text: str, out_wav_path: str) -> Tuple[str, float]:
        try:
            import edge_tts  # noqa: F401  (lazy import)
        except Exception as exc:  # pragma: no cover - network provider
            raise RuntimeError(
                "The 'edge' TTS provider requires the edge-tts package. "
                "Install it with: pip install 'shortsfactory[providers]'  (or: pip install edge-tts). "
                "Note this provider also needs outbound internet access to Microsoft servers."
            ) from exc

        # edge-tts outputs MP3; keep the .mp3 beside the requested path.
        if out_wav_path.lower().endswith(".wav"):
            out_path = out_wav_path[:-4] + ".mp3"
        else:
            out_path = out_wav_path

        try:
            asyncio.run(self._run(text, out_path))
        except Exception as exc:  # pragma: no cover - network provider
            raise RuntimeError(
                "edge-tts synthesis failed. This provider needs outbound internet access "
                "to Microsoft servers, which is not available in offline environments. "
                "Use --provider-tts tone for a fully offline run. "
                f"Underlying error: {exc}"
            ) from exc

        duration = self._probe_duration(out_path)
        return out_path, duration

    async def _run(self, text: str, out_path: str) -> None:  # pragma: no cover
        import edge_tts

        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(out_path)

    @staticmethod
    def _probe_duration(path: str) -> float:  # pragma: no cover - network provider
        # Prefer a lightweight probe via moviepy's audio reader.
        try:
            from moviepy import AudioFileClip

            clip = AudioFileClip(path)
            dur = float(clip.duration)
            clip.close()
            return dur
        except Exception:
            try:
                with wave.open(path, "rb") as wf:
                    return wf.getnframes() / float(wf.getframerate())
            except Exception:
                return 0.0
