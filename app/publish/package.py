"""수동 업로드 패키지 생성 (요구사항 6.1, 6.2, 6.4).

플랫폼 API 권한/승인이 없으므로 자동 업로드가 가능한 것처럼 구현하지 않고,
사람이 각 플랫폼에 직접 올릴 수 있는 패키지를 만든다. 패키지에는 영상 파일과
제목/설명/해시태그/썸네일 문구, 그리고 사용된 소재의 출처·라이선스 표기가 들어간다.

안전장치:
- 승인(approved)된 영상만 패키지/게시 대상 (요구사항 6.4).
- uploads 테이블의 UNIQUE(video_id, platform)로 중복 게시 기록 방지 (요구사항 6.2).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from app.videos_repo import get_video

PLATFORMS = ("youtube", "instagram", "tiktok")


class PublishError(Exception):
    """게시 전제 조건 위반(미승인 등)."""


def _collect_attributions(conn: sqlite3.Connection, video_id: int) -> list[dict]:
    """영상에 사용된 소재의 출처·라이선스 표기 정보를 모은다."""
    rows = conn.execute(
        """
        SELECT a.title, a.author, a.source_url, a.license, a.attribution_required
        FROM video_assets va JOIN assets a ON a.id = va.asset_id
        WHERE va.video_id = ?
        """,
        (video_id,),
    ).fetchall()
    out = []
    for r in rows:
        out.append({
            "title": r["title"],
            "author": r["author"],
            "source_url": r["source_url"],
            "license": r["license"],
            "attribution_required": r["attribution_required"],
        })
    return out


def build_caption(video: dict, attributions: list[dict]) -> str:
    """플랫폼 설명란에 붙여넣을 캡션 텍스트를 만든다(설명 + 해시태그 + 출처표기)."""
    lines = [video.get("title", ""), "", video.get("description", "") or ""]
    hashtags = video.get("hashtags") or []
    if hashtags:
        lines += ["", " ".join(hashtags)]
    # 출처 표기 의무가 있는 소재만 명시
    credits = [a for a in attributions if (a.get("attribution_required") in ("yes", "YES", 1, True))]
    if credits:
        lines += ["", "— 출처 —"]
        for a in credits:
            who = a.get("author") or "작자 미상"
            src = a.get("source_url") or ""
            lic = a.get("license") or ""
            lines.append(f"{who} ({lic}) {src}".strip())
    # AI 생성 콘텐츠 안내(플랫폼 표시 의무 대응)
    lines += ["", "본 영상은 AI 도구를 활용해 제작되었습니다."]
    return "\n".join(lines).strip() + "\n"


def create_package(
    conn: sqlite3.Connection,
    video_id: int,
    out_root: str = "package",
) -> dict:
    """승인된 영상의 수동 업로드 패키지를 생성한다.

    반환: {package_dir, zip_path, files[], caption_path, message}
    """
    video = get_video(conn, video_id)
    if not video:
        raise PublishError("영상을 찾을 수 없습니다.")
    if video.get("status") != "approved":
        raise PublishError(
            "승인되지 않은 영상입니다. 초기 운영 중에는 승인된 영상만 패키지로 만들 수 있습니다. "
            "(대시보드에서 먼저 '승인'하세요.)"
        )
    file_path = video.get("file_path")
    if not file_path or not Path(file_path).exists():
        raise PublishError("영상 파일이 존재하지 않습니다.")

    pkg_dir = Path(out_root) / f"video_{video_id}_{video.get('version', '')}"
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # 1) 영상 파일 복사
    dest_video = pkg_dir / Path(file_path).name
    shutil.copy2(file_path, dest_video)

    # 2) 메타데이터 JSON
    attributions = _collect_attributions(conn, video_id)
    meta = {
        "title": video.get("title"),
        "description": video.get("description"),
        "hashtags": video.get("hashtags"),
        "thumbnail_text": video.get("thumbnail_text"),
        "version": video.get("version"),
        "duration": video.get("duration"),
        "resolution": video.get("resolution"),
        "attributions": attributions,
        "ai_generated": True,
    }
    (pkg_dir / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 3) 플랫폼 설명란용 캡션
    caption = build_caption(video, attributions)
    (pkg_dir / "caption.txt").write_text(caption, encoding="utf-8")

    # 4) 썸네일 문구
    (pkg_dir / "thumbnail_text.txt").write_text(
        (video.get("thumbnail_text") or "") + "\n", encoding="utf-8"
    )

    # 5) 수동 업로드 안내
    guide = (
        "[수동 업로드 안내]\n"
        "플랫폼 자동 업로드 권한이 없어 수동 업로드용 패키지를 생성했습니다.\n"
        "1) 아래 영상 파일을 각 플랫폼(YouTube Shorts / Reels / TikTok)에 직접 업로드하세요.\n"
        f"   - 영상: {dest_video.name}\n"
        "2) caption.txt 내용을 설명란에 붙여넣으세요.\n"
        "3) 각 플랫폼의 AI 생성 콘텐츠 표시 옵션을 켜세요.\n"
        "주의: 이 도구는 수익을 보증하지 않습니다.\n"
    )
    (pkg_dir / "README_업로드안내.txt").write_text(guide, encoding="utf-8")

    # 6) ZIP 압축
    zip_base = str(Path(out_root) / f"video_{video_id}_{video.get('version', '')}")
    zip_path = shutil.make_archive(zip_base, "zip", root_dir=str(pkg_dir))

    files = [p.name for p in sorted(pkg_dir.iterdir())]
    return {
        "package_dir": str(pkg_dir),
        "zip_path": zip_path,
        "files": files,
        "caption_path": str(pkg_dir / "caption.txt"),
        "message": "수동 업로드 패키지를 생성했습니다. (자동 업로드 권한 없음)",
    }


def record_upload(
    conn: sqlite3.Connection,
    video_id: int,
    platform: str,
    status: str = "packaged",
    external_id: str | None = None,
    scheduled_at: str | None = None,
) -> dict:
    """업로드/게시 기록. 중복(video_id+platform)은 갱신한다 (요구사항 6.2, 6.3)."""
    if platform not in PLATFORMS:
        raise PublishError(f"지원하지 않는 플랫폼: {platform}")
    if status not in ("packaged", "uploaded", "failed"):
        raise PublishError(f"잘못된 상태: {status}")
    # UNIQUE(video_id, platform) → 중복이면 UPDATE
    existing = conn.execute(
        "SELECT id FROM uploads WHERE video_id = ? AND platform = ?",
        (video_id, platform),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE uploads SET status = ?, external_id = ?, scheduled_at = ? WHERE id = ?",
            (status, external_id, scheduled_at, existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO uploads (video_id, platform, status, external_id, scheduled_at) "
            "VALUES (?,?,?,?,?)",
            (video_id, platform, status, external_id, scheduled_at),
        )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM uploads WHERE video_id = ? AND platform = ?",
        (video_id, platform),
    ).fetchone()
    return dict(row)


def list_uploads(conn: sqlite3.Connection, video_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM uploads WHERE video_id = ? ORDER BY platform", (video_id,)
    ).fetchall()
    return [dict(r) for r in rows]
