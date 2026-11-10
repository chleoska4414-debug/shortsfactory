"""자막 생성·싱크 (요구사항 3.3).

TTS 단어 타임스탬프(WordMark)와 대본 세그먼트를 결합해 싱크된 자막을 만든다.
숏폼 가독성을 위해 한 줄 길이를 제한하고, 세그먼트 경계를 자막 전환점으로 쓴다.
ASS 포맷으로 출력하여 FFmpeg subtitles 필터로 번인(가독성 있는 하단 배치)한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.providers.script import Script
from app.providers.tts import WordMark


@dataclass
class SubtitleCue:
    start: float
    end: float
    text: str


def build_cues(
    script: Script,
    words: list[WordMark],
    total_duration: float,
    max_chars: int = 18,
) -> list[SubtitleCue]:
    """세그먼트별로 자막 큐를 만든다.

    각 세그먼트의 내레이션을 짧은 줄로 나누고, 단어 타임스탬프로 시작 시각을 추정한다.
    단어 경계가 부족하면 세그먼트 길이를 균등 분배한다.
    """
    cues: list[SubtitleCue] = []

    # 세그먼트별 시작 시각을 단어 타임스탬프로 근사
    seg_texts = [s.narration for s in script.segments]
    seg_starts = _estimate_segment_starts(seg_texts, words, total_duration)

    for i, seg in enumerate(script.segments):
        seg_start = seg_starts[i]
        seg_end = seg_starts[i + 1] if i + 1 < len(seg_starts) else total_duration
        lines = _wrap(seg.narration, max_chars)
        if not lines:
            continue
        span = max(seg_end - seg_start, 0.4)
        per = span / len(lines)
        for j, line in enumerate(lines):
            start = seg_start + j * per
            end = start + per
            cues.append(SubtitleCue(start=round(start, 2), end=round(end, 2), text=line))
    return cues


def _estimate_segment_starts(
    seg_texts: list[str], words: list[WordMark], total: float
) -> list[float]:
    """각 세그먼트의 시작 시각(초)을 추정한다."""
    if words:
        # 단어 수 기반으로 세그먼트 경계의 단어 인덱스를 찾고 그 시각을 사용
        starts = [0.0]
        word_counts = [max(len(t.split()), 1) for t in seg_texts]
        idx = 0
        for wc in word_counts[:-1]:
            idx += wc
            if idx < len(words):
                starts.append(words[idx].start)
            else:
                starts.append(total)
        return starts
    # 타임스탬프 없음 → 글자 수 비례 균등 분배
    total_chars = sum(len(t) for t in seg_texts) or 1
    starts = [0.0]
    acc = 0.0
    for t in seg_texts[:-1]:
        acc += len(t) / total_chars * total
        starts.append(round(acc, 2))
    return starts


def _wrap(text: str, max_chars: int) -> list[str]:
    """내레이션을 숏폼 가독성에 맞게 짧은 줄로 나눈다."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 > max_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def _ass_time(t: float) -> str:
    t = max(t, 0.0)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def write_ass(cues: list[SubtitleCue], out_path: str) -> str:
    """ASS 자막 파일을 생성한다(숏폼 하단, 외곽선/그림자로 가독성 확보).

    PlayRes 1080x1920 기준. 폰트는 FFmpeg가 찾을 수 있는 기본값을 사용.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 2\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
        # 흰 글자 + 검은 외곽선, 하단 중앙(Alignment=2), 아래 여백 넉넉히
        "Style: Default,Sans,64,&H00FFFFFF,&H00000000,&H64000000,"
        "1,1,4,2,2,60,60,320\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    lines = [header]
    for c in cues:
        text = c.text.replace("\n", "\\N")
        lines.append(
            f"Dialogue: 0,{_ass_time(c.start)},{_ass_time(c.end)},Default,,0,0,0,,{text}\n"
        )
    out.write_text("".join(lines), encoding="utf-8")
    return str(out)


def write_srt(cues: list[SubtitleCue], out_path: str) -> str:
    """검수/디버깅용 SRT 자막도 함께 생성."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    def srt_time(t: float) -> str:
        t = max(t, 0.0)
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int((t - int(t)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    blocks = []
    for i, c in enumerate(cues, 1):
        blocks.append(f"{i}\n{srt_time(c.start)} --> {srt_time(c.end)}\n{c.text}\n")
    out.write_text("\n".join(blocks), encoding="utf-8")
    return str(out)
