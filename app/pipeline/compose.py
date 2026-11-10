"""FFmpeg 영상 조립 (요구사항 3.4).

출력 사양: 9:16, 1080x1920, MP4, H.264(libx264), AAC 오디오, 30fps.

이미지 소재 리스트를 받아 각 이미지를 Ken Burns(zoompan)로 동적 처리하고,
세로 캔버스에 맞춰 스케일/크롭한 뒤 이어 붙인다. 그 위에 ASS 자막을 번인하고
내레이션(+선택적 배경음악)을 입힌다.

저작권 관련: 입력 소재는 호출 전에 라이선스 게이트를 통과한 것만 전달된다고 가정한다.
이 모듈은 저작권 회피(반전/배속/크롭 변형)를 수행하지 않는다 — 크롭은 오직 9:16
캔버스 맞춤 목적이다.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

WIDTH, HEIGHT, FPS = 1080, 1920, 30


@dataclass
class ComposeResult:
    output_path: str
    duration: float
    width: int
    height: int
    returncode: int
    log: str


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def compose_video(
    image_paths: list[str],
    audio_path: str,
    subtitle_ass_path: str | None,
    out_path: str,
    total_duration: float,
    bgm_path: str | None = None,
    bgm_volume: float = 0.12,
) -> ComposeResult:
    """이미지 슬라이드 + 자막 + 내레이션으로 세로 영상을 만든다.

    각 이미지는 전체 길이를 균등 분할한 시간만큼 노출되며 Ken Burns 줌이 적용된다.
    """
    settings = get_settings()
    ffmpeg = settings.ffmpeg_path
    if not ffmpeg:
        return ComposeResult(out_path, 0.0, WIDTH, HEIGHT, 1, "FFmpeg 미설치 — 조립 불가")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not image_paths:
        return ComposeResult(out_path, 0.0, WIDTH, HEIGHT, 1, "이미지 소재 없음")

    n = len(image_paths)
    per = max(total_duration / n, 1.0)
    per_frames = int(per * FPS)

    # 입력: 각 이미지를 loop 입력으로
    cmd: list[str] = [ffmpeg, "-y"]
    for img in image_paths:
        cmd += ["-loop", "1", "-t", f"{per:.3f}", "-i", img]
    # 오디오 입력
    cmd += ["-i", audio_path]
    audio_input_idx = n
    if bgm_path:
        cmd += ["-i", bgm_path]
    bgm_input_idx = n + 1 if bgm_path else None

    # 필터 그래프: 각 이미지 스케일/크롭 + Ken Burns zoompan → concat
    filters = []
    for i in range(n):
        # 9:16 캔버스를 덮도록 스케일 후 중앙 크롭, 그 위에 천천히 줌
        filters.append(
            f"[{i}:v]scale={WIDTH*2}:{HEIGHT*2}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH*2}:{HEIGHT*2},"
            f"zoompan=z='min(zoom+0.0008,1.12)':d={per_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={WIDTH}x{HEIGHT}:fps={FPS},"
            f"setsar=1[v{i}]"
        )
    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    filters.append(f"{concat_inputs}concat=n={n}:v=1:a=0[vconcat]")

    # 자막 번인
    if subtitle_ass_path and Path(subtitle_ass_path).exists():
        ass = subtitle_ass_path.replace("\\", "/").replace(":", r"\:")
        filters.append(f"[vconcat]subtitles='{ass}'[vout]")
        vout = "[vout]"
    else:
        vout = "[vconcat]"

    # 오디오: 내레이션 (+ 배경음 ducking 믹스)
    if bgm_input_idx is not None:
        filters.append(
            f"[{bgm_input_idx}:a]volume={bgm_volume}[bgm];"
            f"[{audio_input_idx}:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        amap = "[aout]"
    else:
        amap = f"{audio_input_idx}:a"

    filter_complex = ";".join(filters)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", vout,
        "-map", amap,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(out),
    ]

    proc = _run(cmd)
    duration = _probe_duration(str(out)) if proc.returncode == 0 else 0.0
    # 로그는 끝부분만 보관(과다 방지)
    log = (proc.stderr or "")[-2000:]
    return ComposeResult(
        output_path=str(out),
        duration=duration,
        width=WIDTH,
        height=HEIGHT,
        returncode=proc.returncode,
        log=log,
    )


def _probe_duration(path: str) -> float:
    ffprobe = get_settings().ffprobe_path
    if not ffprobe:
        return 0.0
    try:
        out = _run([
            ffprobe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ], timeout=30)
        return float((out.stdout or "0").strip() or 0.0)
    except (ValueError, subprocess.SubprocessError):
        return 0.0
