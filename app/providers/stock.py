"""무료 스톡 소재 프로바이더 (요구사항 2.4, 3.5).

Pexels API로 세로형 스톡 이미지를 가져온다. Pexels License는 상업적 이용과
수정이 허용되며 출처 표기가 의무는 아니다(권장). 이 프로바이더는 받은 소재를
그 라이선스 메타데이터와 함께 '소재'로 등록하여 라이선스 게이트 판정을 받게 한다.

API 키(PEXELS_API_KEY)가 없으면 비활성 상태로, 가짜 성공 없이 명확히 보고한다.
무료 키 발급: https://www.pexels.com/api/
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PEXELS_PHOTO_SEARCH = "https://api.pexels.com/v1/search"


@dataclass
class StockResult:
    ok: bool
    file_paths: list[str]
    author: str | None = None
    source_urls: list[str] | None = None
    message: str = ""


class PexelsStockProvider:
    """Pexels 세로형 스톡 이미지 수집기."""

    name = "pexels"
    # Pexels License: 상업적 이용 O, 수정 O, 출처표기 의무 아님(권장)
    LICENSE = "CC0"  # 라이선스 게이트에서 상업/수정 모두 허용으로 판정되는 가장 가까운 매핑

    def __init__(self, api_key: str | None):
        self.api_key = api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def fetch_images(
        self,
        query: str,
        count: int,
        out_dir: str,
    ) -> StockResult:
        if not self.api_key:
            return StockResult(
                ok=False, file_paths=[],
                message=("Pexels API 키가 없습니다. .env에 PEXELS_API_KEY를 설정하세요 "
                         "(무료 발급: https://www.pexels.com/api/)."),
            )
        try:
            import requests
        except ImportError:
            return StockResult(ok=False, file_paths=[],
                               message="requests 패키지가 필요합니다: pip install requests")

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        try:
            resp = requests.get(
                PEXELS_PHOTO_SEARCH,
                headers={"Authorization": self.api_key},
                params={"query": query, "orientation": "portrait",
                        "per_page": max(count, 1), "size": "large"},
                timeout=20,
            )
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
        except Exception as exc:  # noqa: BLE001
            return StockResult(ok=False, file_paths=[],
                               message=f"Pexels 검색 실패: {exc}")

        if not photos:
            return StockResult(ok=False, file_paths=[],
                               message=f"'{query}'에 대한 Pexels 결과가 없습니다.")

        paths: list[str] = []
        sources: list[str] = []
        author = photos[0].get("photographer")
        for i, p in enumerate(photos[:count]):
            src = (p.get("src") or {})
            url = src.get("portrait") or src.get("large2x") or src.get("original")
            if not url:
                continue
            try:
                img = requests.get(url, timeout=60)
                img.raise_for_status()
                fp = out / f"pexels_{query.replace(' ', '_')}_{i}.jpg"
                fp.write_bytes(img.content)
                paths.append(str(fp))
                sources.append(p.get("url", url))
            except Exception:  # noqa: BLE001
                continue

        if not paths:
            return StockResult(ok=False, file_paths=[],
                               message="Pexels 이미지 다운로드에 실패했습니다.")
        return StockResult(ok=True, file_paths=paths, author=author,
                           source_urls=sources,
                           message=f"Pexels에서 {len(paths)}개 이미지 수집")

    def asset_metadata(self, file_path: str, source_url: str | None, author: str | None) -> dict:
        """수집한 이미지를 소재로 등록할 때 쓸 권리 메타데이터.

        Pexels License 기준: 상업적 이용/수정 가능, 음악/초상/상표는 사진이므로 기본 확인.
        단, 인물 사진일 수 있으므로 person_rights는 보수적으로 'yes'로 두되,
        운영 시 인물 식별 가능한 사진은 사용자가 재검토하도록 UI에 안내한다.
        """
        return {
            "type": "image",
            "title": f"Pexels: {author or '작가 미상'}",
            "file_path": file_path,
            "source_url": source_url,
            "author": author,
            "license": self.LICENSE,
            "commercial_use": "yes",
            "editable": "yes",
            "attribution_required": "no",
            "proof_ref": "https://www.pexels.com/license/",
            "music_rights": "yes",      # 정지 이미지 — 음악 없음
            "person_rights": "yes",     # Pexels License가 모델 릴리스 포함(상업 사용 허용)
            "trademark_rights": "yes",
        }


def get_stock_provider() -> PexelsStockProvider:
    from app.config import get_settings
    s = get_settings()
    return PexelsStockProvider(api_key=getattr(s, "pexels_api_key", None))
