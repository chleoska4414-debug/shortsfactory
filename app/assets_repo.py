"""소재 저장소 (요구사항 2 + 요구사항 1 연동).

소재를 등록할 때 저작권 판정 엔진(rights.evaluate)을 자동 실행하여
usable 플래그와 사유를 함께 저장한다. 이로써 권리 미확인 소재는
등록 시점에 '사용 불가'로 표시되고, 선택 API에서 자동 제외된다.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from app.rights import AssetRights, evaluate


def _evaluate_payload(data: dict) -> tuple[int, list[str], bool, str | None]:
    rights = AssetRights.from_dict(data)
    decision = evaluate(rights)
    return (
        1 if decision.usable else 0,
        decision.reasons,
        decision.attribution_required,
        decision.attribution_note,
    )


def create_asset(conn: sqlite3.Connection, data: dict) -> dict:
    """소재 등록. 권리 판정을 자동 수행하여 usable/reasons 저장."""
    usable, reasons, attribution_required, _ = _evaluate_payload(data)

    cur = conn.execute(
        """
        INSERT INTO assets (
            type, title, source_url, file_path, author, license,
            commercial_use, editable, attribution_required, proof_ref, expires_at,
            music_rights, person_rights, trademark_rights, usable, reasons
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            data.get("type", "video"),
            data.get("title"),
            data.get("source_url"),
            data.get("file_path"),
            data.get("author"),
            data.get("license"),
            str(data.get("commercial_use", "unknown")),
            str(data.get("editable", "unknown")),
            "yes" if attribution_required else str(data.get("attribution_required", "unknown")),
            data.get("proof_ref"),
            data.get("expires_at"),
            str(data.get("music_rights", "unknown")),
            str(data.get("person_rights", "unknown")),
            str(data.get("trademark_rights", "unknown")),
            usable,
            json.dumps(reasons, ensure_ascii=False),
        ),
    )
    conn.commit()
    return get_asset(conn, cur.lastrowid)


def get_asset(conn: sqlite3.Connection, asset_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_assets(
    conn: sqlite3.Connection,
    asset_type: str | None = None,
    usable_only: bool = False,
) -> list[dict]:
    """소재 목록 조회. 유형/사용가능 필터 지원 (요구사항 2.2)."""
    query = "SELECT * FROM assets WHERE 1=1"
    params: list = []
    if asset_type:
        query += " AND type = ?"
        params.append(asset_type)
    if usable_only:
        query += " AND usable = 1"
    query += " ORDER BY created_at DESC, id DESC"
    rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def select_usable_assets(
    conn: sqlite3.Connection,
    asset_type: str | None = None,
) -> list[dict]:
    """제작 단계에서 사용할, 권리 검증을 통과한 소재만 반환 (요구사항 2.3, 3.5).

    만료일이 지난 소재가 등록 후 만료됐을 수 있으므로 조회 시점에 재판정한다.
    """
    candidates = list_assets(conn, asset_type=asset_type, usable_only=True)
    result = []
    today = date.today()
    for a in candidates:
        rights = AssetRights.from_dict(a)
        if evaluate(rights, today=today).usable:
            result.append(a)
        else:
            # 등록 후 만료 등으로 상태가 바뀐 경우 캐시 갱신 (요구사항 1.5)
            refresh_usable(conn, a["id"])
    return result


def refresh_usable(conn: sqlite3.Connection, asset_id: int) -> dict | None:
    """소재의 권리를 재판정하여 usable/reasons 캐시를 갱신."""
    a = get_asset(conn, asset_id)
    if not a:
        return None
    rights = AssetRights.from_dict(a)
    d = evaluate(rights)
    conn.execute(
        "UPDATE assets SET usable = ?, reasons = ? WHERE id = ?",
        (1 if d.usable else 0, json.dumps(d.reasons, ensure_ascii=False), asset_id),
    )
    conn.commit()
    return get_asset(conn, asset_id)


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if d.get("reasons"):
        try:
            d["reasons"] = json.loads(d["reasons"])
        except (json.JSONDecodeError, TypeError):
            d["reasons"] = [d["reasons"]]
    else:
        d["reasons"] = []
    d["usable"] = bool(d.get("usable"))
    return d
