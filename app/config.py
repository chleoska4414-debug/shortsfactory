"""애플리케이션 설정 로더.

환경 변수(.env)에서 설정을 읽는다. 민감정보(API 키)는 코드에 넣지 않고
.env 에서만 로드한다. 값이 없으면 해당 기능은 "설정 필요" 상태로 비활성화된다.
"""

from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 워크스페이스 루트 (app/ 의 상위)
BASE_DIR = Path(__file__).resolve().parent.parent


def _find_ffmpeg(name: str) -> str | None:
    """PATH 또는 워크스페이스 .tools/ 에서 ffmpeg/ffprobe 바이너리를 찾는다."""
    found = shutil.which(name)
    if found:
        return found
    local = BASE_DIR / ".tools" / name
    if local.exists():
        return str(local)
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_path: str = "data/shorts_studio.sqlite3"

    llm_provider: str = "free"
    tts_provider: str = "free"

    # 선택적 키 (없으면 해당 기능 비활성)
    openai_api_key: str | None = None
    llm_model: str | None = None
    tts_api_key: str | None = None
    tts_voice: str | None = None
    youtube_api_key: str | None = None
    pexels_api_key: str | None = None

    @property
    def db_file(self) -> Path:
        p = Path(self.database_path)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p

    @property
    def ffmpeg_path(self) -> str | None:
        return _find_ffmpeg("ffmpeg")

    @property
    def ffprobe_path(self) -> str | None:
        return _find_ffmpeg("ffprobe")

    def feature_status(self) -> dict[str, dict]:
        """각 기능의 활성/비활성 상태를 반환(가짜 성공 방지, UI 표시용)."""
        return {
            "ffmpeg": {
                "enabled": self.ffmpeg_path is not None,
                "detail": self.ffmpeg_path or "FFmpeg 미설치 — 영상 조립 불가",
            },
            "ffprobe": {
                "enabled": self.ffprobe_path is not None,
                "detail": self.ffprobe_path or "ffprobe 미설치 — 품질 검수 제한",
            },
            "llm_api": {
                "enabled": self.llm_provider == "free" or bool(self.openai_api_key),
                "detail": "무료 프로바이더" if self.llm_provider == "free"
                else ("API 키 설정됨" if self.openai_api_key else "API 키 설정 필요"),
            },
            "tts_api": {
                "enabled": self.tts_provider == "free" or bool(self.tts_api_key),
                "detail": "무료 프로바이더" if self.tts_provider == "free"
                else ("API 키 설정됨" if self.tts_api_key else "API 키 설정 필요"),
            },
            "youtube_trends": {
                "enabled": bool(self.youtube_api_key),
                "detail": "YouTube API 키 설정됨" if self.youtube_api_key
                else "YouTube API 키 설정 필요 — 트렌드 분석 비활성",
            },
            "pexels_stock": {
                "enabled": bool(self.pexels_api_key),
                "detail": "Pexels API 키 설정됨 — 무료 스톡 배경 사용 가능" if self.pexels_api_key
                else "Pexels API 키 설정 필요 — 무료 스톡 배경 비활성 (무료 발급: pexels.com/api)",
            },
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
