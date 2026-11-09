"""Optional network background using the Pexels video API.

Not exercised by the offline test suite. Lazily imports requests and requires a
PEXELS_API_KEY; raises a clear, actionable RuntimeError if the key or network is absent.
"""

from __future__ import annotations

from typing import Optional, Tuple

from .base import BackgroundProvider

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"


class PexelsBackground(BackgroundProvider):
    """Fetch a stock vertical video clip from Pexels. Requires an API key + network."""

    def __init__(self, api_key: Optional[str] = None, query: str = "abstract"):
        self.api_key = api_key
        self.query = query or "abstract"

    def make_clip(self, duration: float, resolution: Tuple[int, int]):
        if not self.api_key:
            raise RuntimeError(
                "The 'pexels' background provider requires a Pexels API key. "
                "Set PEXELS_API_KEY in your .env (get a free key at https://www.pexels.com/api/). "
                "Use --provider-bg gradient for a fully offline run."
            )
        try:
            import requests  # lazy import
        except Exception as exc:  # pragma: no cover - network provider
            raise RuntimeError(
                "The 'pexels' background provider requires the requests package. "
                "Install it with: pip install 'shortsfactory[providers]'  (or: pip install requests)."
            ) from exc

        try:  # pragma: no cover - network provider
            width, height = resolution
            resp = requests.get(
                PEXELS_SEARCH_URL,
                headers={"Authorization": self.api_key},
                params={"query": self.query, "orientation": "portrait", "per_page": 1},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            videos = data.get("videos") or []
            if not videos:
                raise RuntimeError(f"Pexels returned no videos for query '{self.query}'.")
            files = videos[0].get("video_files") or []
            if not files:
                raise RuntimeError("Pexels video had no downloadable files.")
            video_url = files[0]["link"]

            import tempfile

            dl = requests.get(video_url, timeout=60)
            dl.raise_for_status()
            tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            tmp.write(dl.content)
            tmp.close()

            from moviepy import VideoFileClip

            clip = VideoFileClip(tmp.name)
            clip = clip.resized(new_size=(width, height))
            if clip.duration < duration:
                from moviepy import concatenate_videoclips

                loops = int(duration // clip.duration) + 1
                clip = concatenate_videoclips([clip] * loops)
            return clip.subclipped(0, duration)
        except RuntimeError:
            raise
        except Exception as exc:  # pragma: no cover - network provider
            raise RuntimeError(
                "Pexels background fetch failed. This provider needs outbound internet "
                "access, which is not available in offline environments. "
                "Use --provider-bg gradient for a fully offline run. "
                f"Underlying error: {exc}"
            ) from exc
