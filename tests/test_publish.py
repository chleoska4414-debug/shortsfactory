"""게시/업로드 패키지 테스트 (요구사항 6).

승인 게이트, 패키지 생성, 중복 업로드 방지, 출처 표기 캡션을 검증한다.
"""

import zipfile
from pathlib import Path

import pytest

from app.assets_repo import create_asset
from app.db import get_connection, init_db
from app.publish.package import (
    PublishError,
    build_caption,
    create_package,
    list_uploads,
    record_upload,
)
from app.videos_repo import set_status


@pytest.fixture()
def conn(tmp_path):
    db = tmp_path / "t.sqlite3"
    init_db(db)
    c = get_connection(db)
    yield c
    c.close()


def _make_video(conn, tmp_path, status="approved"):
    # 실제 파일이 있어야 패키지가 됨 — 더미 mp4 생성
    f = tmp_path / "v.mp4"
    f.write_bytes(b"\x00\x00\x00\x18ftypmp42dummy")
    cur = conn.execute(
        "INSERT INTO videos (title, description, hashtags, thumbnail_text, version, "
        "status, file_path, duration, resolution) VALUES (?,?,?,?,?,?,?,?,?)",
        ("테스트 영상", "설명입니다", '["#쇼츠","#정보"]', "썸네일문구",
         "A", status, str(f), 31.0, "1080x1920"),
    )
    conn.commit()
    return cur.lastrowid


def test_package_requires_approval(conn, tmp_path):
    vid = _make_video(conn, tmp_path, status="composed")  # 미승인
    with pytest.raises(PublishError):
        create_package(conn, vid, out_root=str(tmp_path / "pkg"))


def test_package_created_for_approved(conn, tmp_path):
    vid = _make_video(conn, tmp_path, status="approved")
    result = create_package(conn, vid, out_root=str(tmp_path / "pkg"))
    assert Path(result["zip_path"]).exists()
    # ZIP 안에 핵심 파일들이 들어있어야 함
    with zipfile.ZipFile(result["zip_path"]) as z:
        names = z.namelist()
    assert any("metadata.json" in n for n in names)
    assert any("caption.txt" in n for n in names)
    assert any(n.endswith(".mp4") for n in names)


def test_record_upload_prevents_duplicates(conn, tmp_path):
    vid = _make_video(conn, tmp_path)
    record_upload(conn, vid, "youtube", status="packaged")
    record_upload(conn, vid, "youtube", status="uploaded")  # 같은 (video,platform)
    ups = [u for u in list_uploads(conn, vid) if u["platform"] == "youtube"]
    assert len(ups) == 1  # 중복 생성 안 됨
    assert ups[0]["status"] == "uploaded"  # 갱신됨


def test_record_upload_rejects_bad_platform(conn, tmp_path):
    vid = _make_video(conn, tmp_path)
    with pytest.raises(PublishError):
        record_upload(conn, vid, "facebook")


def test_caption_includes_attribution_and_ai_notice(conn, tmp_path):
    vid = _make_video(conn, tmp_path)
    # 출처표기 의무 있는 소재 연결
    asset = create_asset(conn, {
        "type": "image", "title": "사진", "author": "홍길동",
        "source_url": "https://ex.com/1", "license": "CC BY",
        "attribution_required": "yes",
        "music_rights": "yes", "person_rights": "yes", "trademark_rights": "yes",
    })
    conn.execute("INSERT INTO video_assets (video_id, asset_id) VALUES (?,?)",
                 (vid, asset["id"]))
    conn.commit()
    from app.videos_repo import get_video
    from app.publish.package import _collect_attributions
    video = get_video(conn, vid)
    caption = build_caption(video, _collect_attributions(conn, vid))
    assert "홍길동" in caption
    assert "출처" in caption
    assert "AI" in caption  # AI 생성 안내 포함
