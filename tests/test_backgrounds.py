"""로컬 생성 그라데이션 배경 테스트.

FFmpeg가 있어야 실제 생성이 되므로, 없으면 skip. 생성된 이미지가
1080x1920인지 ffprobe로 확인한다.
"""

import subprocess

import pytest

from app.config import get_settings
from app.pipeline.backgrounds import GRADIENT_THEMES, generate_gradient_backgrounds

_ffmpeg = get_settings().ffmpeg_path
_ffprobe = get_settings().ffprobe_path

needs_ffmpeg = pytest.mark.skipif(
    not (_ffmpeg and _ffprobe), reason="FFmpeg/ffprobe 필요"
)


def test_themes_defined():
    # 최소 몇 개의 선명한 색 조합이 정의돼 있어야 영상마다 변화를 줄 수 있다
    assert len(GRADIENT_THEMES) >= 3
    for c0, c1 in GRADIENT_THEMES:
        assert c0.startswith("0x") and c1.startswith("0x")


@needs_ffmpeg
def test_generate_gradient_backgrounds(tmp_path):
    paths = generate_gradient_backgrounds(3, str(tmp_path / "bg"))
    assert len(paths) == 3
    for p in paths:
        out = subprocess.run(
            [_ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0", p],
            capture_output=True, text=True, timeout=30,
        )
        assert "1080,1920" in out.stdout


@needs_ffmpeg
def test_generate_cycles_themes(tmp_path):
    # 테마 수보다 많이 요청해도 순환하며 모두 생성
    n = len(GRADIENT_THEMES) + 2
    paths = generate_gradient_backgrounds(n, str(tmp_path / "bg2"))
    assert len(paths) == n
