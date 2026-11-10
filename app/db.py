"""SQLite 데이터 계층.

design.md의 데이터 모델을 구현한다. 표준 라이브러리 sqlite3만 사용하여
의존성을 최소화한다. 스키마는 최초 연결 시 생성된다(idempotent).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,                      -- video | image | music | sfx
    title TEXT,
    source_url TEXT,
    file_path TEXT,
    author TEXT,
    license TEXT,
    commercial_use TEXT DEFAULT 'unknown',
    editable TEXT DEFAULT 'unknown',
    attribution_required TEXT DEFAULT 'unknown',
    proof_ref TEXT,
    expires_at TEXT,
    music_rights TEXT DEFAULT 'unknown',
    person_rights TEXT DEFAULT 'unknown',
    trademark_rights TEXT DEFAULT 'unknown',
    usable INTEGER DEFAULT 0,                 -- 판정 결과 캐시 (0/1)
    reasons TEXT,                             -- 사용불가 사유 (JSON 문자열)
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    source_signals TEXT,
    status TEXT DEFAULT 'new',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id INTEGER,
    title TEXT,
    description TEXT,
    hashtags TEXT,
    thumbnail_text TEXT,
    version TEXT,                             -- A | B
    status TEXT DEFAULT 'draft',             -- draft|composed|qc_pending|held|approved|published
    file_path TEXT,
    duration REAL,
    resolution TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (idea_id) REFERENCES ideas(id)
);

CREATE TABLE IF NOT EXISTS video_assets (
    video_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    PRIMARY KEY (video_id, asset_id),
    FOREIGN KEY (video_id) REFERENCES videos(id),
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

CREATE TABLE IF NOT EXISTS qc_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    check_name TEXT NOT NULL,
    result TEXT NOT NULL,                     -- pass | warn | fail
    detail TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (video_id) REFERENCES videos(id)
);

CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    platform TEXT NOT NULL,                   -- youtube | instagram | tiktok
    status TEXT DEFAULT 'packaged',           -- packaged | uploaded | failed
    external_id TEXT,
    scheduled_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE (video_id, platform),              -- 중복 업로드 방지
    FOREIGN KEY (video_id) REFERENCES videos(id)
);

CREATE TABLE IF NOT EXISTS costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER,
    item TEXT NOT NULL,
    provider TEXT,
    amount REAL DEFAULT 0,
    currency TEXT DEFAULT 'KRW',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (video_id) REFERENCES videos(id)
);

CREATE TABLE IF NOT EXISTS performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    is_estimate INTEGER DEFAULT 0,            -- 추정치 여부 (확인치와 구분)
    fetched_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (video_id) REFERENCES videos(id)
);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """DB 연결을 반환한다(스키마 보장). Row 접근은 딕셔너리처럼 가능."""
    path = db_path or get_settings().db_file
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path | None = None) -> None:
    """스키마를 생성한다(이미 있으면 무시)."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"DB 초기화 완료: {get_settings().db_file}")
