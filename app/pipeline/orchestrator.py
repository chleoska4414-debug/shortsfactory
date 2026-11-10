"""제작 오케스트레이터 (Task 4.8) — 주제 → 영상 1편 end-to-end.

단계: 대본 생성 → TTS 내레이션 → 자막 싱크 → 소재 선택(라이선스 게이트) → FFmpeg 조립.
사용 가능한 이미지 소재가 부족하면 제작을 중단하고 부족분을 보고한다(요구사항 3.8).

이미지 소재가 전혀 없을 때를 대비해, 요청 시 단색+텍스트 플레이스홀더 이미지를
생성하는 보조 기능을 제공한다(검증/데모용. 실제 운영은 권리 확인된 소재 사용).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.assets_repo import select_usable_assets
from app.pipeline.backgrounds import generate_gradient_backgrounds
from app.pipeline.compose import compose_video
from app.pipeline.subtitles import build_cues, write_ass, write_srt
from app.providers.script import get_script_provider
from app.providers.tts import get_tts_provider, pick_voice_for_tone


@dataclass
class ProduceResult:
    ok: bool
    version: str
    topic: str
    output_path: str | None = None
    duration: float = 0.0
    title: str = ""
    description: str = ""
    hashtags: list[str] = field(default_factory=list)
    thumbnail_text: str = ""
    used_asset_ids: list[int] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    srt_path: str | None = None


def produce_video(
    conn: sqlite3.Connection,
    topic: str,
    version: str = "A",
    tone: str = "info",
    work_dir: str = "output",
    bgm_asset: dict | None = None,
    allow_placeholder_images: bool = False,
    fetch_stock: bool = True,
    use_generated_backgrounds: bool = True,
) -> ProduceResult:
    version = version.upper()
    messages: list[str] = []
    work = Path(work_dir) / f"{_slug(topic)}_{version}"
    work.mkdir(parents=True, exist_ok=True)

    # 1) 대본
    script = get_script_provider().generate(topic, version=version, tone=tone)
    messages.append(f"대본 생성 완료 (provider={script.provider}, 세그먼트 {len(script.segments)}개)")

    # 2) TTS 내레이션
    tts = get_tts_provider()
    voice = pick_voice_for_tone(tone)
    audio_path = str(work / "narration.mp3")
    try:
        tts_result = tts.synthesize(script.full_narration, audio_path, voice=voice)
    except Exception as e:  # noqa: BLE001 - 외부 서비스 실패는 held 처리
        return ProduceResult(
            ok=False, version=version, topic=topic,
            messages=messages + [f"TTS 실패: {e}"],
        )
    messages.append(
        f"TTS 완료 (voice={tts_result.voice}, {tts_result.duration:.1f}초, "
        f"단어 {len(tts_result.words)}개)"
    )

    # 3) 자막 싱크
    cues = build_cues(script, tts_result.words, tts_result.duration)
    ass_path = write_ass(cues, str(work / "subtitle.ass"))
    srt_path = write_srt(cues, str(work / "subtitle.srt"))
    messages.append(f"자막 생성 완료 ({len(cues)}개 큐)")

    # 4) 소재 선택 (라이선스 게이트) — 세그먼트 수만큼 이미지 필요
    needed = len(script.segments)
    usable_images = select_usable_assets(conn, asset_type="image")
    image_paths = [a["file_path"] for a in usable_images if a.get("file_path")][:needed]
    used_asset_ids = [a["id"] for a in usable_images if a.get("file_path")][:needed]

    # 4-b) 부족하면 무료 스톡(Pexels)에서 보충 — 받은 소재도 라이선스 게이트를 통과해야 등록됨
    if len(image_paths) < needed and fetch_stock:
        fetched = _fetch_stock_assets(
            conn, topic, needed - len(image_paths),
            str(Path(work_dir) / "_stock"),
        )
        for msg in fetched["messages"]:
            messages.append(msg)
        if fetched["asset_ids"]:
            usable_images = select_usable_assets(conn, asset_type="image")
            image_paths = [a["file_path"] for a in usable_images if a.get("file_path")][:needed]
            used_asset_ids = [a["id"] for a in usable_images if a.get("file_path")][:needed]

    # 4-c) 아직 부족하면 프로그램이 직접 생성한 그라데이션 배경으로 보충.
    #      직접 생성물이라 제3자 권리 문제가 없어 플레이스홀더보다 우선한다.
    if len(image_paths) < needed and use_generated_backgrounds:
        shortfall = needed - len(image_paths)
        bgs = generate_gradient_backgrounds(shortfall, str(work / "_bg"))
        if bgs:
            image_paths += bgs
            messages.append(
                f"권리확인 소재 부족 {shortfall}개 → 직접 생성한 그라데이션 배경으로 보충 "
                f"(지식카드형, 저작권 문제 없음)."
            )

    if len(image_paths) < needed:
        shortfall = needed - len(image_paths)
        if allow_placeholder_images:
            ph = _make_placeholders(script, work, shortfall)
            image_paths += ph
            messages.append(
                f"[주의] 권리확인 이미지 {shortfall}개 부족 → 데모용 플레이스홀더로 대체. "
                f"실제 게시 전 권리확인 소재로 교체 필요."
            )
        else:
            messages.append(
                f"사용 가능한 이미지 소재 부족: {len(image_paths)}/{needed}. "
                f"권리 확인된 이미지 {shortfall}개를 추가하세요. (요구사항 3.8)"
            )
            return ProduceResult(
                ok=False, version=version, topic=topic, messages=messages,
            )

    # 5) FFmpeg 조립
    out_path = str(work / f"video_{version}.mp4")
    bgm_path = bgm_asset.get("file_path") if bgm_asset else None
    comp = compose_video(
        image_paths=image_paths,
        audio_path=audio_path,
        subtitle_ass_path=ass_path,
        out_path=out_path,
        total_duration=max(tts_result.duration, 1.0),
        bgm_path=bgm_path,
    )
    if comp.returncode != 0:
        messages.append(f"FFmpeg 조립 실패: {comp.log[-400:]}")
        return ProduceResult(ok=False, version=version, topic=topic, messages=messages)

    messages.append(
        f"영상 조립 완료: {comp.width}x{comp.height}, {comp.duration:.1f}초"
    )
    return ProduceResult(
        ok=True,
        version=version,
        topic=topic,
        output_path=comp.output_path,
        duration=comp.duration,
        title=script.title,
        description=script.description,
        hashtags=script.hashtags,
        thumbnail_text=script.thumbnail_text,
        used_asset_ids=used_asset_ids,
        messages=messages,
        srt_path=srt_path,
    )


def _fetch_stock_assets(conn, query: str, count: int, out_dir: str) -> dict:
    """Pexels 무료 스톡 이미지를 받아 소재로 등록(라이선스 게이트 통과한 것만 사용 가능).

    키가 없거나 네트워크 실패 시 가짜 성공 없이 사유를 메시지로 반환한다.
    """
    from app.assets_repo import create_asset
    from app.providers.stock import get_stock_provider

    provider = get_stock_provider()
    if not provider.enabled:
        return {"asset_ids": [],
                "messages": ["무료 스톡 배경 비활성: .env에 PEXELS_API_KEY를 설정하면 "
                             "주제에 맞는 상업적 이용 가능 이미지를 자동 수집합니다."]}

    result = provider.fetch_images(query, count, out_dir)
    if not result.ok:
        return {"asset_ids": [], "messages": [f"스톡 수집 실패: {result.message}"]}

    asset_ids: list[int] = []
    for i, fp in enumerate(result.file_paths):
        src = result.source_urls[i] if result.source_urls and i < len(result.source_urls) else None
        meta = provider.asset_metadata(fp, src, result.author)
        asset = create_asset(conn, meta)  # 라이선스 판정 자동 수행
        if asset["usable"]:
            asset_ids.append(asset["id"])
    return {"asset_ids": asset_ids,
            "messages": [f"{result.message} → 권리판정 통과 {len(asset_ids)}개 등록"]}


def _slug(text: str) -> str:
    keep = [c if c.isalnum() else "_" for c in text.strip()]
    return "".join(keep)[:40] or "video"


def _make_placeholders(script, work: Path, count: int) -> list[str]:
    """데모/검증용 단색 그라데이션 플레이스홀더 이미지를 FFmpeg로 생성.

    실제 운영에서는 사용하지 않는다(권리 확인된 소재만 사용).
    """
    from app.config import get_settings
    import subprocess

    ffmpeg = get_settings().ffmpeg_path
    paths: list[str] = []
    colors = ["0x1b2a4a", "0x3a1b4a", "0x1b4a3a", "0x4a3a1b", "0x4a1b2a", "0x1b3a4a"]
    for i in range(count):
        p = str(work / f"placeholder_{i}.png")
        color = colors[i % len(colors)]
        if ffmpeg:
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i",
                 f"color=c={color}:s=1080x1920:d=1", "-frames:v", "1", p],
                capture_output=True, text=True, timeout=30,
            )
        paths.append(p)
    return paths
