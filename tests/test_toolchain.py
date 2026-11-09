"""Toolchain smoke tests: verify the package imports and the offline media toolchain works.

These tests must run fully offline with no system ffmpeg installed. ffmpeg is provided by
the pip package imageio-ffmpeg (a static bundled binary), which is what moviepy uses.
"""

import os


def test_package_imports_with_version():
    import shortsfactory

    assert shortsfactory.__version__ == "0.1.0"


def test_bundled_ffmpeg_is_available():
    import imageio_ffmpeg

    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    assert ffmpeg_path
    assert os.path.exists(ffmpeg_path), f"bundled ffmpeg not found at {ffmpeg_path}"
