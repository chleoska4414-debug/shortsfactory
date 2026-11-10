"""로컬 생성 배경 (키·외부 소재 불필요).

외부 스톡 없이도 완성도 있는 "지식카드형" 숏폼을 만들기 위해 FFmpeg로
세로형(1080x1920) 그라데이션 배경 이미지를 생성한다. 세그먼트마다 다른
색 조합을 써서 영상에 시각적 변화를 준다.

저작권: 모두 프로그램이 직접 생성한 이미지이므로 제3자 권리 문제가 없다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import get_settings

WIDTH, HEIGHT = 1080, 1920

# 선명한 2색 대각선 그라데이션 조합. 채도 있는 색이라 시각적 변화가 크고,
# 하단에 어두운 오버레이를 깔아 흰 자막 가독성을 확보한다.
GRADIENT_THEMES: list[tuple[str, str]] = [
    ("0x2E4FD8", "0x7B2FF7"),   # 블루 → 바이올렛
    ("0xF7414F", "0x7B2FF7"),   # 레드핑크 → 퍼플
    ("0x00B894", "0x0984E3"),   # 에메랄드 → 블루
    ("0xFF7B2F", "0xF7414F"),   # 오렌지 → 레드
    ("0x0984E3", "0x00CEC9"),   # 블루 → 시안
    ("0x6C5CE7", "0xE84393"),   # 인디고 → 마젠타
    ("0xE17055", "0xFDCB6E"),   # 코랄 → 골드
]


def generate_gradient_backgrounds(count: int, out_dir: str) -> list[str]:
    """count개의 선명한 대각선 그라데이션 배경 PNG를 생성해 경로 리스트를 반환한다.

    gradients 필터로 2색 대각선 그라데이션을 만든 뒤, 하단 절반에 어두운
    선형 오버레이를 합성해 자막 영역의 대비를 확보한다. 실패 시 단색 폴백.
    """
    ffmpeg = get_settings().ffmpeg_path
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    for i in range(count):
        c0, c1 = GRADIENT_THEMES[i % len(GRADIENT_THEMES)]
        fp = out / f"bg_gradient_{i}.png"
        ok = False
        if ffmpeg:
            # 대각선(좌상→우하) 2색 그라데이션 + 하단을 어둡게 하는 수직 그라데이션 오버레이
            filter_complex = (
                f"gradients=s={WIDTH}x{HEIGHT}:c0={c0}:c1={c1}"
                f":x0=0:y0=0:x1={WIDTH}:y1={HEIGHT}:nb_colors=2[base];"
                f"gradients=s={WIDTH}x{HEIGHT}:c0=0x00000000:c1=0x000000CC"
                f":x0=0:y0=0:x1=0:y1={HEIGHT}:nb_colors=2[shade];"
                f"[base][shade]overlay=format=auto[out]"
            )
            cmd = [
                ffmpeg, "-y",
                "-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:d=1",
                "-filter_complex", filter_complex,
                "-map", "[out]", "-frames:v", "1", str(fp),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            ok = proc.returncode == 0 and fp.exists()
            if not ok:
                # 폴백: 단순 대각선 그라데이션
                subprocess.run(
                    [ffmpeg, "-y", "-f", "lavfi",
                     "-i", (f"gradients=s={WIDTH}x{HEIGHT}:c0={c0}:c1={c1}"
                            f":x0=0:y0=0:x1={WIDTH}:y1={HEIGHT}:nb_colors=2"),
                     "-frames:v", "1", str(fp)],
                    capture_output=True, text=True, timeout=60,
                )
                ok = fp.exists()
        if ok:
            paths.append(str(fp))
    return paths
