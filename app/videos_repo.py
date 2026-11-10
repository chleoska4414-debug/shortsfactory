"""영상 저장소 — 제작 결과를 DB에 기록하고 승인 상태를 관리한다.

요구사항 6.4/7.3: 초기에는 사용자가 승인한 영상만 게시/패키지 대상이 된다.
"""

from __future__ import annotations

import json
import sqlite3


def save_video(conn: sqlite3.Connection, result, status: str = "composed") -> dict:
    """ProduceResult를 videos 테이블에 저장하고 사용 소재를 연결한다."""
    cur = conn.execute(
        """
        INSERT INTO videos (title, description, hashtags, thumbnail_text,
                            version, status, file_path, duration, resolution)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            result.title,
            result.description,
            json.dumps(result.hashtags, ensure_ascii=False),
            result.thumbnail_text,
            result.version,
            status,
            result.output_path,
            result.duration,
            "1080x1920",
        ),
    )
    video_id = cur.lastrowid
    for aid in result.used_asset_ids:
        conn.execute(
            "INSERT OR IGNORE INTO video_assets (video_id, asset_id) VALUES (?,?)",
            (video_id, aid),
        )
    conn.commit()
    return get_video(conn, video_id)


def get_video(conn: sqlite3.Connection, video_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    return _row(row) if row else None


def list_videos(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    q = "SELECT * FROM videos"
    params: list = []
    if status:
        q += " WHERE status = ?"
        params.append(status)
    q += " ORDER BY created_at DESC, id DESC"
    return [_row(r) for r in conn.execute(q, params).fetchall()]


def set_status(conn: sqlite3.Connection, video_id: int, status: str) -> dict | None:
    """영상 상태 변경. 승인(approved)은 사용자 액션으로만 호출된다."""
    allowed = {"draft", "composed", "qc_pending", "held", "approved", "published"}
    if status not in allowed:
        raise ValueError(f"잘못된 상태: {status}")
    conn.execute("UPDATE videos SET status = ? WHERE id = ?", (status, video_id))
    conn.commit()
    return get_video(conn, video_id)


def _row(row: sqlite3.Row) -> dict:
    d = dict(row)
    if d.get("hashtags"):
        try:
            d["hashtags"] = json.loads(d["hashtags"])
        except (json.JSONDecodeError, TypeError):
            d["hashtags"] = []
    else:
        d["hashtags"] = []
    return d
