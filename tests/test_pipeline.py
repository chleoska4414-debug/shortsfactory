"""영상 제작 파이프라인 통합 테스트 (Task 4.8).

FFmpeg/edge-tts가 사용 가능한 환경에서만 실행된다(없으면 skip).
플레이스홀더 이미지를 사용해 실제 MP4를 조립하고 사양(9:16, 1080x1920, h264)을 검증한다.
"""

import subprocess

import pytest

from app.config import get_settings
from app.db import get_connection, init_db
from app.pipeline.subtitles import build_cues, write_ass
from app.providers.script import TemplateScriptProvider

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


# --- 외부 도구 없이도 가능한 로직 테스트 ---

def test_script_ab_versions_differ():
    p = TemplateScriptProvider()
    a = p.generate("테스트 주제", "A")
    b = p.generate("테스트 주제", "B")
    assert a.version == "A" and b.version == "B"
    # A/B는 단순 길이 조절이 아니라 세그먼트 구성이 다름 (요구사항 3.7)
    assert len(b.segments) > len(a.segments)
    assert a.title != b.title


def test_script_b_is_substantially_longer_than_a():
    # B 대본은 A보다 내레이션 분량이 뚜렷이 많아야 목표 길이(65~90초)에 도달 (Task 4.9)
    p = TemplateScriptProvider()
    a = p.generate("아침 루틴", "A")
    b = p.generate("아침 루틴", "B")
    len_a = len(a.full_narration)
    len_b = len(b.full_narration)
    # B 내레이션 글자수가 A의 2배 이상이어야 길이 목표 달성에 유리
    assert len_b >= len_a * 2, f"A={len_a}자, B={len_b}자 — B가 충분히 길지 않음"


def test_subtitle_cues_from_words():
    from app.providers.tts import WordMark
    p = TemplateScriptProvider()
    script = p.generate("자막 테스트", "A")
    words = [WordMark(start=i * 0.5, text=f"w{i}") for i in range(20)]
    cues = build_cues(script, words, total_duration=10.0)
    assert len(cues) > 0
    # 시작 시각이 단조 증가
    starts = [c.start for c in cues]
    assert starts == sorted(starts)


def test_write_ass(tmp_path):
    from app.pipeline.subtitles import SubtitleCue
    cues = [SubtitleCue(0.0, 1.0, "안녕하세요"), SubtitleCue(1.0, 2.0, "테스트")]
    out = tmp_path / "s.ass"
    write_ass(cues, str(out))
    content = out.read_text(encoding="utf-8")
    assert "[Events]" in content
    assert "안녕하세요" in content


# --- 전체 파이프라인 (미디어 도구 필요) ---

@needs_media
def test_full_pipeline_produces_valid_mp4(conn, tmp_path):
    from app.pipeline.orchestrator import produce_video

    r = produce_video(
        conn, "통합 테스트 주제", version="A", tone="info",
        work_dir=str(tmp_path / "out"), allow_placeholder_images=True,
    )
    assert r.ok, f"제작 실패: {r.messages}"
    assert r.output_path and r.duration > 0

    # ffprobe로 사양 검증
    out = subprocess.run(
        [_ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,codec_name",
         "-of", "default=noprint_wrappers=1:nokey=1", r.output_path],
        capture_output=True, text=True, timeout=30,
    )
    vals = out.stdout.split()
    assert "h264" in vals
    assert "1080" in vals
    assert "1920" in vals


def test_korean_font_bundled():
    # 한글 자막 렌더링에 필요한 번들 폰트가 존재해야 한다(두부 현상 방지).
    from app.pipeline.compose import FONTS_DIR
    font = FONTS_DIR / "NanumGothic-Regular.ttf"
    assert font.exists(), "번들 한글 폰트(NanumGothic)가 없습니다 — 자막이 깨집니다"
    assert font.stat().st_size > 100_000


def test_ass_uses_korean_font():
    # ASS 스타일이 한글 폰트를 지정하는지 확인
    from app.pipeline.subtitles import SubtitleCue, write_ass
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".ass")
    os.close(fd)
    write_ass([SubtitleCue(0.0, 1.0, "한글 자막")], path)
    content = open(path, encoding="utf-8").read()
    os.unlink(path)
    assert "NanumGothic" in content


@needs_media
def test_pipeline_blocks_without_usable_images(conn, tmp_path):
    # 생성배경·스톡·플레이스홀더 모두 비활성 + 권리확인 이미지 없음 → 제작 중단 (요구사항 3.8)
    from app.pipeline.orchestrator import produce_video

    r = produce_video(
        conn, "소재부족 테스트", version="A",
        work_dir=str(tmp_path / "out2"), allow_placeholder_images=False,
        fetch_stock=False, use_generated_backgrounds=False,
    )
    assert r.ok is False
    assert any("부족" in m for m in r.messages)


@needs_media
def test_pipeline_uses_generated_backgrounds(conn, tmp_path):
    # 소재가 없어도 생성 그라데이션 배경으로 영상이 완성돼야 한다 (플레이스홀더 없이)
    from app.pipeline.orchestrator import produce_video

    r = produce_video(
        conn, "배경 생성 테스트", version="A",
        work_dir=str(tmp_path / "out3"), allow_placeholder_images=False,
        fetch_stock=False, use_generated_backgrounds=True,
    )
    assert r.ok is True
    assert r.output_path and r.duration > 0
    assert any("그라데이션 배경" in m for m in r.messages)
