"""품질 검수(QC) 테스트 (요구사항 4).

- 순수 로직 검사(라이선스 증빙, 싱크/길이/해상도, 독창성, AI 표시)는 외부 도구 없이 검증.
- fail 있으면 held 전환되는 통합 동작을 모의 소재로 검증.
- 실제 미디어 분석(ffprobe/ffmpeg)은 가용 환경에서만 실행(없으면 skip) — test_pipeline.py 패턴.
"""

import json

import pytest

from app.assets_repo import create_asset
from app.config import get_settings
from app.db import get_connection, init_db
from app.qc.checks import (
    FAIL,
    PASS,
    WARN,
    check_ai_disclosure,
    check_duration,
    check_license_proof,
    check_resolution,
    check_script_originality,
    check_subtitle_sync,
    get_qc_results,
    run_qc,
)

_settings = get_settings()
_ffmpeg = _settings.ffmpeg_path
_ffprobe = _settings.ffprobe_path

try:
    import edge_tts  # noqa: F401
    _has_edge = True
except ImportError:
    _has_edge = False

needs_media = pytest.mark.skipif(
    not (_ffmpeg and _ffprobe and _has_edge),
    reason="FFmpeg/ffprobe/edge-tts 필요",
)


@pytest.fixture()
def conn(tmp_path):
    db = tmp_path / "t.sqlite3"
    init_db(db)
    c = get_connection(db)
    yield c
    c.close()


def _insert_video(conn, version="A", status="composed", file_path=None):
    cur = conn.execute(
        "INSERT INTO videos (title, version, status, file_path, resolution) "
        "VALUES (?,?,?,?,?)",
        ("테스트 영상", version, status, file_path, "1080x1920"),
    )
    conn.commit()
    return cur.lastrowid


# --- 길이 검사 ---

def test_duration_within_range_passes():
    assert check_duration(35.0, "A").result == PASS
    assert check_duration(80.0, "B").result == PASS


def test_duration_out_of_range_warns():
    assert check_duration(10.0, "A").result == WARN   # 너무 짧음
    assert check_duration(120.0, "B").result == WARN  # 너무 김


def test_duration_unknown_warns():
    assert check_duration(None, "A").result == WARN
    assert check_duration(0.0, "A").result == WARN


# --- 해상도 검사 ---

def test_resolution_correct_passes():
    assert check_resolution(1080, 1920).result == PASS


def test_resolution_wrong_fails():
    o = check_resolution(1920, 1080)
    assert o.result == FAIL


def test_resolution_unknown_warns():
    assert check_resolution(None, None).result == WARN


# --- 싱크 검사 ---

def test_sync_within_tolerance_passes():
    assert check_subtitle_sync(29.5, 30.0).result == PASS


def test_sync_subtitle_exceeds_media_warns():
    o = check_subtitle_sync(33.0, 30.0)
    assert o.result == WARN
    assert "초과" in o.detail


def test_sync_large_deviation_warns():
    assert check_subtitle_sync(25.0, 30.0).result == WARN


def test_sync_unknown_warns():
    assert check_subtitle_sync(None, 30.0).result == WARN
    assert check_subtitle_sync(30.0, None).result == WARN


# --- 독창성 검사 ---

def test_originality_no_source_is_unverifiable():
    o = check_script_originality("원본 대본 텍스트입니다", None)
    assert o.result == WARN
    assert "확인 불가" in o.detail


def test_originality_high_overlap_warns():
    text = "물을 자주 마시면 피부와 건강에 좋습니다 매일 꾸준히 실천하세요"
    o = check_script_originality(text, text, n=3)
    assert o.result == WARN


def test_originality_distinct_passes():
    a = "완전히 다른 주제의 독창적인 한국어 대본 문장 구성입니다"
    b = "서로 겹치지 않는 별개의 소스 텍스트 내용을 담고 있어요"
    assert check_script_originality(a, b, n=3).result == PASS


# --- AI 표시 의무 ---

def test_ai_disclosure_not_set_warns():
    assert check_ai_disclosure(disclosed=False).result == WARN


def test_ai_disclosure_set_passes():
    assert check_ai_disclosure(disclosed=True).result == PASS


# --- 라이선스 증빙 검사 ---

def test_license_proof_no_assets_warns(conn):
    vid = _insert_video(conn)
    o = check_license_proof(conn, vid)
    assert o.result == WARN


def test_license_proof_unusable_asset_fails(conn):
    vid = _insert_video(conn)
    # 권리 미확인 소재 → usable=False
    bad = create_asset(conn, {"type": "image", "title": "권리미확인 이미지",
                              "license": None, "file_path": "/tmp/bad.png"})
    assert bad["usable"] is False
    conn.execute("INSERT INTO video_assets (video_id, asset_id) VALUES (?,?)",
                 (vid, bad["id"]))
    conn.commit()
    o = check_license_proof(conn, vid)
    assert o.result == FAIL
    assert "미통과" in o.detail


def test_license_proof_usable_asset_passes(conn):
    vid = _insert_video(conn)
    good = create_asset(conn, {
        "type": "image", "title": "CC0 이미지", "license": "CC0",
        "file_path": "/tmp/good.png",
        "music_rights": "yes", "person_rights": "yes", "trademark_rights": "yes",
    })
    assert good["usable"] is True
    conn.execute("INSERT INTO video_assets (video_id, asset_id) VALUES (?,?)",
                 (vid, good["id"]))
    conn.commit()
    assert check_license_proof(conn, vid).result == PASS


# --- run_qc 통합: fail 있으면 held 전환 ---

def test_run_qc_holds_on_fail(conn):
    # 파일 경로 없음 → 미디어 검사는 warn, 하지만 사용 불가 소재로 license_proof=fail
    vid = _insert_video(conn, status="composed", file_path=None)
    bad = create_asset(conn, {"type": "image", "title": "불가 소재",
                              "license": "CC BY-NC", "file_path": "/tmp/x.png"})
    assert bad["usable"] is False
    conn.execute("INSERT INTO video_assets (video_id, asset_id) VALUES (?,?)",
                 (vid, bad["id"]))
    conn.commit()

    report = run_qc(conn, vid)
    assert report.has_fail is True
    assert report.passed is False
    assert report.status == "held"

    # DB 상태도 held 로 바뀌어야 함
    row = conn.execute("SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()
    assert row["status"] == "held"

    # 결과가 qc_results 에 기록됐는지
    results = get_qc_results(conn, vid)
    assert len(results) >= 1
    names = {r["check_name"] for r in results}
    assert "license_proof" in names


def test_run_qc_no_fail_does_not_hold(conn):
    # 사용 가능 소재만 연결 + 파일 없음(미디어 검사는 warn) → fail 없음 → held 아님
    vid = _insert_video(conn, status="composed", file_path=None)
    good = create_asset(conn, {
        "type": "image", "title": "CC0", "license": "CC0", "file_path": "/tmp/g.png",
        "music_rights": "yes", "person_rights": "yes", "trademark_rights": "yes",
    })
    conn.execute("INSERT INTO video_assets (video_id, asset_id) VALUES (?,?)",
                 (vid, good["id"]))
    conn.commit()

    report = run_qc(conn, vid)
    assert report.has_fail is False
    assert report.passed is True
    assert report.status != "held"
    row = conn.execute("SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()
    assert row["status"] == "composed"


def test_run_qc_unknown_video_raises(conn):
    with pytest.raises(ValueError):
        run_qc(conn, 99999)


# --- 실제 미디어 통합(가용 시) ---

@needs_media
def test_run_qc_on_real_video_holds_wrong_resolution(conn, tmp_path):
    # 실제 1080x1920 영상을 만들면 해상도 pass, 하지만 플레이스홀더 영상은
    # 검은 화면/저볼륨으로 fail/warn 가능. 핵심은 ffprobe/ffmpeg 가 실제로 돌아가는지.
    from app.pipeline.orchestrator import produce_video
    from app.videos_repo import save_video

    r = produce_video(
        conn, "큐씨 통합 테스트", version="A",
        work_dir=str(tmp_path / "out"),
        allow_placeholder_images=True, fetch_stock=False,
    )
    assert r.ok, f"제작 실패: {r.messages}"
    video = save_video(conn, r, status="composed")

    report = run_qc(conn, video["id"], script_text=r.title)
    names = {o.check_name: o.result for o in report.outcomes}
    # 해상도는 실제로 측정되어 pass 여야 함
    assert names.get("resolution") == PASS
    # 길이/볼륨/검은화면 등 모든 결과가 기록됨
    assert len(get_qc_results(conn, video["id"])) == len(report.outcomes)
