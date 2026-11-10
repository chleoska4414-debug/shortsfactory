"""QC 검사 엔진 (요구사항 4).

검사 항목:
- 검은 화면: FFmpeg `blackdetect`
- 음성 볼륨: FFmpeg `volumedetect` (무음/저볼륨 감지)
- 영상 길이: ffprobe (버전별 목표 범위)
- 해상도: ffprobe (1080x1920 고정)
- 음성·자막 싱크: 자막 마지막 큐 종료시각 vs 미디어 길이 비교
- 저작권/라이선스 증빙: video_assets 로 연결된 모든 소재 재판정(usable)
- 대본 독창성: 대본 vs 소스 텍스트 n-gram 중복률(소스 없으면 '확인 불가')
- 플랫폼 AI 표시 의무: 체크리스트 항목(통과/미설정)

규칙:
- fail 이 하나라도 있으면 영상 상태를 held 로 전환(통과 금지).
- fail 없이 warn 만 있으면 통과시키되 warn 기록.
- 모두 pass면 통과(상태 변경은 하지 않음 — 승인은 사용자 몫).

수익화 가능성을 보증하는 표현은 넣지 않는다(요구사항 4.5).
각 검사 결과(pass|warn|fail + detail)는 qc_results 테이블에 기록한다.

미디어 분석(ffprobe/ffmpeg)은 app.config 의 경로를 사용하고 subprocess + timeout 으로
호출한다. 바이너리가 없으면 해당 검사는 warn('확인 불가')으로 처리한다(가짜 성공 금지).
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.assets_repo import get_asset
from app.config import get_settings
from app.rights import AssetRights, evaluate
from app.videos_repo import get_video, set_status

# 결과 상태 상수
PASS = "pass"
WARN = "warn"
FAIL = "fail"

# 버전별 목표 길이 범위(초) — 요구사항 3.7 (A: 25~45초, B: 65~90초)
DURATION_TARGETS: dict[str, tuple[float, float]] = {
    "A": (25.0, 45.0),
    "B": (65.0, 90.0),
}

# 기대 해상도 (요구사항 3.4)
EXPECTED_WIDTH = 1080
EXPECTED_HEIGHT = 1920

# 음성·자막 싱크 허용 편차(초). 자막 종료가 미디어 길이보다 이만큼 이상
# 벗어나면 경고한다.
SYNC_TOLERANCE_SEC = 1.5

# 볼륨 기준(dB). mean_volume 이 이 값보다 낮으면 너무 작은 것으로 본다.
MIN_MEAN_VOLUME_DB = -35.0

# 외부 프로세스 타임아웃(초)
FFPROBE_TIMEOUT = 30
FFMPEG_TIMEOUT = 120

# 플랫폼별 AI 생성 콘텐츠 표시 의무 체크리스트 (요구사항 4.4)
AI_DISCLOSURE_PLATFORMS = ("youtube", "instagram", "tiktok")


@dataclass
class CheckOutcome:
    """단일 검사 결과."""

    check_name: str
    result: str          # pass | warn | fail
    detail: str = ""

    def as_dict(self) -> dict:
        return {"check_name": self.check_name, "result": self.result, "detail": self.detail}


@dataclass
class QCReport:
    """전체 QC 결과."""

    video_id: int
    outcomes: list[CheckOutcome] = field(default_factory=list)
    status: str = ""          # 검수 후 영상 상태
    passed: bool = False       # fail 이 없으면 True

    @property
    def has_fail(self) -> bool:
        return any(o.result == FAIL for o in self.outcomes)

    @property
    def has_warn(self) -> bool:
        return any(o.result == WARN for o in self.outcomes)

    def as_dict(self) -> dict:
        return {
            "video_id": self.video_id,
            "status": self.status,
            "passed": self.passed,
            "results": [o.as_dict() for o in self.outcomes],
        }


# --------------------------------------------------------------------------
# 순수 로직 검사 (외부 도구 불필요 — 단위 테스트 가능)
# --------------------------------------------------------------------------

def check_license_proof(conn: sqlite3.Connection, video_id: int) -> CheckOutcome:
    """해당 영상에 연결된 모든 소재가 라이선스 게이트를 통과(usable)하는지 재확인.

    하나라도 사용 불가면 fail. 연결된 소재가 없으면 warn(증빙 없음).
    (요구사항 4.1 — 저작권/라이선스 증빙 존재)
    """
    rows = conn.execute(
        "SELECT asset_id FROM video_assets WHERE video_id = ?", (video_id,)
    ).fetchall()
    asset_ids = [r["asset_id"] for r in rows]

    if not asset_ids:
        return CheckOutcome(
            "license_proof", WARN,
            "연결된 소재 증빙이 없습니다. 사용된 소재의 권리 정보를 확인하세요.",
        )

    bad: list[str] = []
    for aid in asset_ids:
        asset = get_asset(conn, aid)
        if asset is None:
            bad.append(f"소재 {aid}: 레코드 없음")
            continue
        decision = evaluate(AssetRights.from_dict(asset))
        if not decision.usable:
            reason = ", ".join(decision.reasons) or "사용 불가"
            title = asset.get("title") or asset.get("file_path") or f"소재 {aid}"
            bad.append(f"{title}: {reason}")

    if bad:
        return CheckOutcome(
            "license_proof", FAIL,
            "라이선스 게이트 미통과 소재: " + " / ".join(bad),
        )
    return CheckOutcome(
        "license_proof", PASS,
        f"연결된 소재 {len(asset_ids)}개 모두 라이선스 게이트 통과.",
    )


def check_subtitle_sync(
    subtitle_last_end: float | None,
    media_duration: float | None,
    tolerance: float = SYNC_TOLERANCE_SEC,
) -> CheckOutcome:
    """자막 마지막 큐 종료시각과 미디어 길이의 편차를 점검한다(요구사항 4.1).

    - 자막 또는 미디어 길이를 알 수 없으면 warn('확인 불가').
    - 편차가 허용치를 넘으면 warn(싱크 어긋남 가능).
    - 자막이 미디어보다 길면(잘림 위험) 편차와 무관하게 warn.
    """
    if subtitle_last_end is None or media_duration is None or media_duration <= 0:
        return CheckOutcome(
            "subtitle_sync", WARN,
            "자막 또는 영상 길이 정보를 확인할 수 없어 싱크 점검 불가.",
        )
    diff = subtitle_last_end - media_duration
    if subtitle_last_end > media_duration + 0.05:
        return CheckOutcome(
            "subtitle_sync", WARN,
            f"자막 종료({subtitle_last_end:.2f}s)가 영상 길이({media_duration:.2f}s)를 "
            f"초과 — 자막 잘림 위험.",
        )
    if abs(diff) > tolerance:
        return CheckOutcome(
            "subtitle_sync", WARN,
            f"자막 종료와 영상 길이 편차 {abs(diff):.2f}s "
            f"(허용 {tolerance:.1f}s) — 싱크 확인 권장.",
        )
    return CheckOutcome(
        "subtitle_sync", PASS,
        f"자막 종료({subtitle_last_end:.2f}s)와 영상 길이({media_duration:.2f}s) 편차 "
        f"{abs(diff):.2f}s — 양호.",
    )


def check_duration(
    media_duration: float | None,
    version: str | None,
    targets: dict[str, tuple[float, float]] | None = None,
) -> CheckOutcome:
    """영상 길이가 버전별 목표 범위 안에 있는지 점검(요구사항 3.7, 4.1).

    범위를 벗어나면 warn(길이 조정 권장). 길이를 알 수 없으면 warn.
    목표 범위가 정의되지 않은 버전이면 0초 초과만 확인.
    """
    targets = targets or DURATION_TARGETS
    if media_duration is None or media_duration <= 0:
        return CheckOutcome("duration", WARN, "영상 길이 정보를 확인할 수 없습니다.")

    ver = (version or "").upper()
    rng = targets.get(ver)
    if rng is None:
        return CheckOutcome(
            "duration", PASS,
            f"영상 길이 {media_duration:.1f}s (버전 '{ver or '미지정'}' 목표 범위 없음).",
        )
    lo, hi = rng
    if media_duration < lo:
        return CheckOutcome(
            "duration", WARN,
            f"영상 길이 {media_duration:.1f}s 가 버전 {ver} 목표({lo:.0f}~{hi:.0f}s)보다 짧음.",
        )
    if media_duration > hi:
        return CheckOutcome(
            "duration", WARN,
            f"영상 길이 {media_duration:.1f}s 가 버전 {ver} 목표({lo:.0f}~{hi:.0f}s)보다 김.",
        )
    return CheckOutcome(
        "duration", PASS,
        f"영상 길이 {media_duration:.1f}s — 버전 {ver} 목표({lo:.0f}~{hi:.0f}s) 충족.",
    )


def check_resolution(width: int | None, height: int | None) -> CheckOutcome:
    """해상도가 1080x1920(9:16)인지 점검(요구사항 3.4, 4.1).

    다르면 fail. 정보를 알 수 없으면 warn.
    """
    if not width or not height:
        return CheckOutcome("resolution", WARN, "해상도 정보를 확인할 수 없습니다.")
    if width == EXPECTED_WIDTH and height == EXPECTED_HEIGHT:
        return CheckOutcome("resolution", PASS, f"해상도 {width}x{height} (9:16) 충족.")
    return CheckOutcome(
        "resolution", FAIL,
        f"해상도 {width}x{height} 가 요구사항({EXPECTED_WIDTH}x{EXPECTED_HEIGHT})과 다릅니다.",
    )


def check_script_originality(
    script_text: str | None,
    source_text: str | None,
    n: int = 5,
    warn_ratio: float = 0.35,
) -> CheckOutcome:
    """대본과 비교 소스 텍스트의 n-gram 중복률을 간단 점검(요구사항 4.2).

    - 비교 소스가 없으면 '확인 불가'(warn) — 추측하지 않는다(요구사항 5.2 정신).
    - 중복률이 임계값을 초과하면 warn(복제 위험).
    """
    if not script_text or not script_text.strip():
        return CheckOutcome("script_originality", WARN, "대본 텍스트가 없어 독창성 점검 불가.")
    if not source_text or not source_text.strip():
        return CheckOutcome(
            "script_originality", WARN,
            "비교할 외부 소스 텍스트가 없어 중복 여부 확인 불가(확인 불가).",
        )

    ratio = _ngram_overlap_ratio(script_text, source_text, n=n)
    if ratio > warn_ratio:
        return CheckOutcome(
            "script_originality", WARN,
            f"대본과 소스의 {n}-gram 중복률 {ratio * 100:.0f}% — "
            f"실질적 복제 위험, 재작성 권장.",
        )
    return CheckOutcome(
        "script_originality", PASS,
        f"대본과 소스의 {n}-gram 중복률 {ratio * 100:.0f}% — 독창성 양호.",
    )


def check_ai_disclosure(
    platforms: tuple[str, ...] = AI_DISCLOSURE_PLATFORMS,
    disclosed: bool = False,
) -> CheckOutcome:
    """플랫폼별 AI 생성 콘텐츠 표시 의무 체크리스트(요구사항 4.4).

    체크리스트 항목을 제공하되, 설정되지 않았으면 warn(미설정)으로 표시한다.
    수익화 가능성을 보증하는 표현은 넣지 않는다(요구사항 4.5).
    """
    items = ", ".join(platforms)
    if disclosed:
        return CheckOutcome(
            "ai_disclosure", PASS,
            f"AI 생성 콘텐츠 표시 설정됨 — 업로드 시 각 플랫폼({items})에 표기 적용.",
        )
    return CheckOutcome(
        "ai_disclosure", WARN,
        f"AI 생성 콘텐츠 표시 미설정 — 업로드 전 각 플랫폼({items})의 "
        f"AI 콘텐츠 표시 의무를 확인·설정하세요.",
    )


def _ngram_overlap_ratio(a: str, b: str, n: int = 5) -> float:
    """a 의 n-gram 중 b 에도 등장하는 비율(0.0~1.0)."""
    ga = _ngrams(a, n)
    gb = set(_ngrams(b, n))
    if not ga:
        return 0.0
    hits = sum(1 for g in ga if g in gb)
    return hits / len(ga)


def _ngrams(text: str, n: int) -> list[tuple[str, ...]]:
    tokens = _tokenize(text)
    if len(tokens) < n:
        return [tuple(tokens)] if tokens else []
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def _tokenize(text: str) -> list[str]:
    # 한글/영문/숫자 단위로 토큰화(구두점 제거)
    return re.findall(r"[0-9A-Za-z가-힣]+", text.lower())


# --------------------------------------------------------------------------
# 미디어 분석 (ffprobe/ffmpeg 필요)
# --------------------------------------------------------------------------

def probe_media(path: str) -> dict:
    """ffprobe 로 비디오 폭/높이/길이를 추출한다.

    반환: {"width": int|None, "height": int|None, "duration": float|None,
           "available": bool, "error": str|None}
    바이너리가 없거나 실패하면 available=False.
    """
    ffprobe = get_settings().ffprobe_path
    info: dict = {"width": None, "height": None, "duration": None,
                  "available": False, "error": None}
    if not ffprobe:
        info["error"] = "ffprobe 미설치"
        return info
    if not path or not Path(path).exists():
        info["error"] = "영상 파일 없음"
        return info
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-print_format", "json",
             "-show_streams", "-show_format", path],
            capture_output=True, text=True, timeout=FFPROBE_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError) as e:  # noqa: BLE001
        info["error"] = f"ffprobe 실행 실패: {e}"
        return info
    if proc.returncode != 0:
        info["error"] = f"ffprobe 오류: {proc.stderr[-200:]}"
        return info

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as e:
        info["error"] = f"ffprobe 출력 파싱 실패: {e}"
        return info

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            info["width"] = _to_int(stream.get("width"))
            info["height"] = _to_int(stream.get("height"))
            break
    duration = data.get("format", {}).get("duration")
    info["duration"] = _to_float(duration)
    info["available"] = True
    return info


def detect_black_frames(path: str) -> CheckOutcome:
    """FFmpeg blackdetect 로 검은 화면 구간을 탐지한다(요구사항 4.1).

    검은 구간이 검출되면 fail, 없으면 pass. 도구가 없으면 warn('확인 불가').
    """
    ffmpeg = get_settings().ffmpeg_path
    if not ffmpeg:
        return CheckOutcome("black_frames", WARN, "FFmpeg 미설치 — 검은 화면 확인 불가.")
    if not path or not Path(path).exists():
        return CheckOutcome("black_frames", WARN, "영상 파일이 없어 검은 화면 확인 불가.")
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", path,
             "-vf", "blackdetect=d=0.5:pix_th=0.10", "-an", "-f", "null", "-"],
            capture_output=True, text=True, timeout=FFMPEG_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError) as e:  # noqa: BLE001
        return CheckOutcome("black_frames", WARN, f"검은 화면 분석 실행 실패: {e}")

    matches = re.findall(r"black_start:(\d+\.?\d*)\s+black_end:(\d+\.?\d*)", proc.stderr)
    if matches:
        spans = ", ".join(f"{s}~{e}s" for s, e in matches[:5])
        return CheckOutcome(
            "black_frames", FAIL,
            f"검은 화면 구간 {len(matches)}개 검출: {spans}",
        )
    return CheckOutcome("black_frames", PASS, "검은 화면 구간이 검출되지 않았습니다.")


def detect_volume(path: str) -> CheckOutcome:
    """FFmpeg volumedetect 로 음성 볼륨을 점검한다(요구사항 4.1).

    - 오디오가 없거나 mean_volume 이 매우 낮으면(무음 수준) fail.
    - mean_volume 이 기준(MIN_MEAN_VOLUME_DB)보다 낮으면 warn(너무 작음).
    - 도구가 없으면 warn('확인 불가').
    """
    ffmpeg = get_settings().ffmpeg_path
    if not ffmpeg:
        return CheckOutcome("volume", WARN, "FFmpeg 미설치 — 음성 볼륨 확인 불가.")
    if not path or not Path(path).exists():
        return CheckOutcome("volume", WARN, "영상 파일이 없어 음성 볼륨 확인 불가.")
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", path, "-af", "volumedetect",
             "-vn", "-f", "null", "-"],
            capture_output=True, text=True, timeout=FFMPEG_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError) as e:  # noqa: BLE001
        return CheckOutcome("volume", WARN, f"볼륨 분석 실행 실패: {e}")

    stderr = proc.stderr
    if "volumedetect" not in stderr and "mean_volume" not in stderr:
        return CheckOutcome("volume", FAIL, "오디오 트랙이 없거나 볼륨을 측정할 수 없습니다.")

    mean_m = re.search(r"mean_volume:\s*(-?\d+\.?\d*)\s*dB", stderr)
    max_m = re.search(r"max_volume:\s*(-?\d+\.?\d*)\s*dB", stderr)
    mean = _to_float(mean_m.group(1)) if mean_m else None
    maxv = _to_float(max_m.group(1)) if max_m else None

    if mean is None:
        return CheckOutcome("volume", WARN, "평균 볼륨을 파싱할 수 없습니다.")
    if maxv is not None and maxv <= -90.0:
        return CheckOutcome("volume", FAIL, f"사실상 무음(최대 {maxv:.1f}dB) — 음성 확인 필요.")
    if mean < MIN_MEAN_VOLUME_DB:
        return CheckOutcome(
            "volume", WARN,
            f"평균 볼륨 {mean:.1f}dB 가 기준({MIN_MEAN_VOLUME_DB:.0f}dB)보다 낮음 — "
            f"볼륨 보정 권장.",
        )
    return CheckOutcome("volume", PASS, f"평균 볼륨 {mean:.1f}dB — 양호.")


# --------------------------------------------------------------------------
# 진입점
# --------------------------------------------------------------------------

def run_qc(
    conn: sqlite3.Connection,
    video_id: int,
    *,
    subtitle_path: str | None = None,
    source_text: str | None = None,
    script_text: str | None = None,
    ai_disclosed: bool = False,
    target_duration_range: dict[str, tuple[float, float]] | None = None,
) -> QCReport:
    """영상 1편에 대해 전체 QC를 실행한다.

    - 영상 파일과 DB 정보를 받아 각 검사를 수행한다.
    - 각 검사 결과를 qc_results 테이블에 기록한다.
    - fail 이 하나라도 있으면 영상 status 를 held 로 전환한다(통과 금지, 요구사항 4.3).
    - fail 이 없으면 통과(상태는 바꾸지 않음 — 승인은 사용자 몫).

    subtitle_path 가 없으면 영상 파일과 같은 폴더의 subtitle.srt/ass 를 자동 탐색한다.
    """
    video = get_video(conn, video_id)
    if video is None:
        raise ValueError(f"영상을 찾을 수 없습니다: {video_id}")

    file_path = video.get("file_path")
    version = video.get("version")
    outcomes: list[CheckOutcome] = []

    # 1) 미디어 분석 (ffprobe)
    probe = probe_media(file_path) if file_path else {
        "width": None, "height": None, "duration": None, "available": False}
    media_duration = probe.get("duration")

    # 길이/해상도
    outcomes.append(check_duration(media_duration, version, target_duration_range))
    outcomes.append(check_resolution(probe.get("width"), probe.get("height")))

    # 2) 검은 화면 / 볼륨 (ffmpeg)
    outcomes.append(detect_black_frames(file_path or ""))
    outcomes.append(detect_volume(file_path or ""))

    # 3) 음성·자막 싱크
    sub_path = subtitle_path or _find_subtitle(file_path)
    sub_end = _last_cue_end(sub_path) if sub_path else None
    outcomes.append(check_subtitle_sync(sub_end, media_duration))

    # 4) 저작권/라이선스 증빙
    outcomes.append(check_license_proof(conn, video_id))

    # 5) 대본 독창성
    outcomes.append(check_script_originality(script_text, source_text))

    # 6) AI 표시 의무 체크리스트
    outcomes.append(check_ai_disclosure(disclosed=ai_disclosed))

    # 결과 기록
    _record_results(conn, video_id, outcomes)

    report = QCReport(video_id=video_id, outcomes=outcomes)
    report.passed = not report.has_fail

    # fail 이 있으면 held 전환 (요구사항 4.3)
    if report.has_fail:
        updated = set_status(conn, video_id, "held")
        report.status = updated["status"] if updated else "held"
    else:
        report.status = video.get("status", "")

    return report


def _record_results(
    conn: sqlite3.Connection, video_id: int, outcomes: list[CheckOutcome]
) -> None:
    """검사 결과를 qc_results 테이블에 기록한다."""
    for o in outcomes:
        conn.execute(
            "INSERT INTO qc_results (video_id, check_name, result, detail) "
            "VALUES (?,?,?,?)",
            (video_id, o.check_name, o.result, o.detail),
        )
    conn.commit()


def get_qc_results(conn: sqlite3.Connection, video_id: int) -> list[dict]:
    """영상의 QC 결과 기록을 최신순으로 반환한다."""
    rows = conn.execute(
        "SELECT id, video_id, check_name, result, detail, created_at "
        "FROM qc_results WHERE video_id = ? ORDER BY id DESC",
        (video_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _find_subtitle(file_path: str | None) -> str | None:
    """영상 파일과 같은 폴더에서 subtitle.srt/ass 를 탐색한다."""
    if not file_path:
        return None
    folder = Path(file_path).parent
    for name in ("subtitle.srt", "subtitle.ass"):
        cand = folder / name
        if cand.exists():
            return str(cand)
    return None


def _last_cue_end(subtitle_path: str) -> float | None:
    """SRT 또는 ASS 자막에서 마지막 큐의 종료시각(초)을 추출한다."""
    p = Path(subtitle_path)
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8", errors="ignore")
    if p.suffix.lower() == ".ass":
        return _last_ass_end(text)
    return _last_srt_end(text)


def _last_srt_end(text: str) -> float | None:
    ends = re.findall(r"-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})", text)
    if not ends:
        return None
    h, m, s, ms = ends[-1]
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _last_ass_end(text: str) -> float | None:
    # Dialogue: Layer, Start, End, ...  (End 는 3번째 필드)
    last: float | None = None
    for line in text.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",")
        if len(parts) < 3:
            continue
        end = _ass_time_to_sec(parts[2].strip())
        if end is not None:
            last = end
    return last


def _ass_time_to_sec(t: str) -> float | None:
    m = re.match(r"(\d+):(\d{2}):(\d{2})\.(\d{1,2})", t)
    if not m:
        return None
    h, mi, s, cs = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(cs) / (10 ** len(cs))


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
