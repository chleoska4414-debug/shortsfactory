"""TTS 프로바이더 (요구사항 3.2, 3.3).

무료 기본 구현: edge-tts (Microsoft Edge 온라인 TTS, 무료, 한국어 자연스러움).
WordBoundary 옵션으로 단어별 타임스탬프를 수집하여 자막 싱크에 사용한다.

각 synthesize() 호출은 (오디오 파일 경로, 단어 타임스탬프 리스트, 총 길이초)를 반환한다.
키가 필요 없으므로 플랜 A에서 비용 0원으로 동작한다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# 상황별 추천 음성 (요구사항: "상황에 맞는 TTS")
# 콘텐츠 톤에 따라 자동/수동 선택 가능
KOREAN_VOICES = {
    "default": "ko-KR-SunHiNeural",       # 밝고 친근한 여성 — 범용/정보성
    "female_friendly": "ko-KR-SunHiNeural",
    "male_calm": "ko-KR-InJoonNeural",    # 차분한 남성 — 해설/다큐형
    "male_warm": "ko-KR-HyunsuMultilingualNeural",  # 따뜻한 남성 — 스토리텔링
}


def pick_voice_for_tone(tone: str | None) -> str:
    """콘텐츠 톤에 맞는 음성을 자동 선택한다.

    tone 예: 'info'(정보), 'story'(스토리텔링), 'doc'(해설/다큐), 'fun'(가벼움)
    """
    mapping = {
        "info": KOREAN_VOICES["female_friendly"],
        "fun": KOREAN_VOICES["female_friendly"],
        "story": KOREAN_VOICES["male_warm"],
        "doc": KOREAN_VOICES["male_calm"],
        "calm": KOREAN_VOICES["male_calm"],
    }
    return mapping.get((tone or "").lower(), KOREAN_VOICES["default"])


@dataclass
class WordMark:
    """단어별 타임스탬프 (초 단위)."""

    start: float
    text: str


@dataclass
class TTSResult:
    audio_path: str
    words: list[WordMark]
    duration: float
    voice: str
    provider: str


class TTSProvider(Protocol):
    def synthesize(self, text: str, out_path: str, voice: str | None = None) -> TTSResult:
        ...


class EdgeTTSProvider:
    """무료 edge-tts 기반 구현."""

    name = "edge-tts(free)"

    def __init__(self, default_voice: str | None = None):
        self.default_voice = default_voice or KOREAN_VOICES["default"]

    def synthesize(self, text: str, out_path: str, voice: str | None = None) -> TTSResult:
        import edge_tts  # 지연 임포트 (설치 안 돼도 다른 기능 동작)

        voice = voice or self.default_voice
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        async def _run() -> list[WordMark]:
            comm = edge_tts.Communicate(text, voice, boundary="WordBoundary")
            words: list[WordMark] = []
            with open(out, "wb") as f:
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        words.append(WordMark(start=chunk["offset"] / 1e7, text=chunk["text"]))
            return words

        words = asyncio.run(_run())
        duration = self._probe_duration(str(out))
        return TTSResult(
            audio_path=str(out),
            words=words,
            duration=duration,
            voice=voice,
            provider=self.name,
        )

    @staticmethod
    def _probe_duration(path: str) -> float:
        import subprocess

        from app.config import get_settings

        ffprobe = get_settings().ffprobe_path
        if not ffprobe:
            return 0.0
        try:
            out = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=30,
            )
            return float(out.stdout.strip() or 0.0)
        except (ValueError, subprocess.SubprocessError):
            return 0.0


def get_tts_provider() -> TTSProvider:
    """설정에 따라 TTS 프로바이더를 반환한다.

    현재 무료(edge-tts)만 구현. 유료 API 프로바이더는 키가 설정되면 여기서 분기한다.
    """
    from app.config import get_settings

    settings = get_settings()
    # 향후: if settings.tts_provider == "api" and settings.tts_api_key: return ApiTTSProvider(...)
    return EdgeTTSProvider(default_voice=settings.tts_voice)
