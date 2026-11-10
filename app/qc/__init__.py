"""품질 검수(QC) 모듈 (요구사항 4).

업로드 전 영상을 자동 검사해 결함이 있으면 "보류(held)"로 처리한다.
핵심 진입점은 run_qc(conn, video_id, ...) 이며, 각 검사 결과를 qc_results 테이블에
기록하고 fail이 하나라도 있으면 영상 status를 held로 전환한다.
"""

from __future__ import annotations

from app.qc.checks import (
    CheckOutcome,
    QCReport,
    check_license_proof,
    check_subtitle_sync,
    check_duration,
    check_resolution,
    run_qc,
    DURATION_TARGETS,
)

__all__ = [
    "CheckOutcome",
    "QCReport",
    "run_qc",
    "check_license_proof",
    "check_subtitle_sync",
    "check_duration",
    "check_resolution",
    "DURATION_TARGETS",
]
