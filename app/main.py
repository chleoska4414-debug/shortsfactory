"""FastAPI 앱 — 대시보드 + REST API (Task 1.3, 3.1, 5).

단일 로컬 애플리케이션이 한국어 대시보드와 제작 API를 모두 제공한다.
실행: uvicorn app.main:app --reload  (또는 run.py)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import __version__
from app.assets_repo import create_asset, list_assets, select_usable_assets
from app.config import get_settings
from app.db import get_connection, init_db
from app.pipeline.orchestrator import produce_video
from app.qc import run_qc
from app.qc.checks import get_qc_results
from app.videos_repo import list_videos, save_video, set_status

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="AI 숏폼 자동 수익화 스튜디오", version=__version__)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    (BASE_DIR / "output").mkdir(exist_ok=True)


# 완성 영상/산출물 정적 서빙 (미리보기용)
app.mount("/media", StaticFiles(directory=str(BASE_DIR / "output")), name="media")


# ---------- 모델 ----------

class AssetIn(BaseModel):
    type: str = "image"
    title: str | None = None
    source_url: str | None = None
    file_path: str | None = None
    author: str | None = None
    license: str | None = None
    commercial_use: str = "unknown"
    editable: str = "unknown"
    attribution_required: str = "unknown"
    proof_ref: str | None = None
    expires_at: str | None = None
    music_rights: str = "unknown"
    person_rights: str = "unknown"
    trademark_rights: str = "unknown"


class ProduceIn(BaseModel):
    topic: str
    version: str = "A"
    tone: str = "info"
    allow_placeholder_images: bool = False
    fetch_stock: bool = True
    use_generated_backgrounds: bool = True


class QCIn(BaseModel):
    # 선택 입력 — 독창성 비교 소스, 대본 텍스트, AI 표시 설정 여부
    source_text: str | None = None
    script_text: str | None = None
    ai_disclosed: bool = False


# ---------- 상태 ----------

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__,
            "features": get_settings().feature_status()}


# ---------- 소재 (요구사항 2) ----------

@app.get("/api/assets")
def api_list_assets(type: str | None = None, usable_only: bool = False) -> dict:
    conn = get_connection()
    try:
        return {"assets": list_assets(conn, asset_type=type, usable_only=usable_only)}
    finally:
        conn.close()


@app.post("/api/assets")
def api_create_asset(payload: AssetIn) -> dict:
    conn = get_connection()
    try:
        asset = create_asset(conn, payload.model_dump())
        return {"asset": asset}
    finally:
        conn.close()


# ---------- 제작 (요구사항 3) ----------

@app.post("/api/produce")
def api_produce(payload: ProduceIn) -> dict:
    conn = get_connection()
    try:
        result = produce_video(
            conn, payload.topic, version=payload.version, tone=payload.tone,
            allow_placeholder_images=payload.allow_placeholder_images,
            fetch_stock=payload.fetch_stock,
            use_generated_backgrounds=payload.use_generated_backgrounds,
        )
        if not result.ok:
            return {"ok": False, "messages": result.messages}
        video = save_video(conn, result, status="composed")
        return {"ok": True, "messages": result.messages, "video": video}
    finally:
        conn.close()


# ---------- 영상 (요구사항 7) ----------

@app.get("/api/videos")
def api_list_videos(status: str | None = None) -> dict:
    conn = get_connection()
    try:
        return {"videos": list_videos(conn, status=status)}
    finally:
        conn.close()


@app.post("/api/videos/{video_id}/approve")
def api_approve(video_id: int) -> dict:
    # 요구사항 6.4/7.3: 사용자 승인으로만 approved 전환
    conn = get_connection()
    try:
        v = set_status(conn, video_id, "approved")
        if not v:
            raise HTTPException(404, "영상을 찾을 수 없습니다")
        return {"video": v}
    finally:
        conn.close()


@app.post("/api/videos/{video_id}/qc")
def api_run_qc(video_id: int, payload: QCIn | None = None) -> dict:
    # 요구사항 4: 업로드 전 자동 검수. fail 이 있으면 영상은 held 로 전환된다.
    from app.videos_repo import get_video

    body = payload or QCIn()
    conn = get_connection()
    try:
        if get_video(conn, video_id) is None:
            raise HTTPException(404, "영상을 찾을 수 없습니다")
        report = run_qc(
            conn, video_id,
            source_text=body.source_text,
            script_text=body.script_text,
            ai_disclosed=body.ai_disclosed,
        )
        return {"qc": report.as_dict()}
    finally:
        conn.close()


@app.get("/api/videos/{video_id}/qc")
def api_get_qc(video_id: int) -> dict:
    from app.videos_repo import get_video

    conn = get_connection()
    try:
        if get_video(conn, video_id) is None:
            raise HTTPException(404, "영상을 찾을 수 없습니다")
        return {"results": get_qc_results(conn, video_id)}
    finally:
        conn.close()


@app.get("/api/videos/{video_id}/file")
def api_video_file(video_id: int):
    from app.videos_repo import get_video
    conn = get_connection()
    try:
        v = get_video(conn, video_id)
    finally:
        conn.close()
    if not v or not v.get("file_path") or not Path(v["file_path"]).exists():
        raise HTTPException(404, "영상 파일이 없습니다")
    return FileResponse(v["file_path"], media_type="video/mp4")


# ---------- 대시보드 ----------

@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    html_path = BASE_DIR / "app" / "web" / "dashboard.html"
    return html_path.read_text(encoding="utf-8")
