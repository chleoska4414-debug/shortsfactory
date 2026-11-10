"""무료 스톡(Pexels) 프로바이더 테스트.

네트워크/키가 없는 환경에서도 '가짜 성공' 없이 올바르게 비활성 동작하는지,
그리고 받은 소재의 권리 메타데이터가 라이선스 게이트를 통과하는지 검증한다.
실제 네트워크 호출은 하지 않는다(키 없는 경로 + 메타데이터 판정만 검사).
"""

from app.providers.stock import PexelsStockProvider
from app.rights import AssetRights, evaluate


def test_disabled_without_key():
    p = PexelsStockProvider(api_key=None)
    assert p.enabled is False
    r = p.fetch_images("바다", 3, "/tmp/stock_test")
    assert r.ok is False
    assert "PEXELS_API_KEY" in r.message  # 명확한 안내, 가짜 성공 아님


def test_asset_metadata_passes_license_gate():
    # Pexels 메타데이터로 만든 소재는 라이선스 게이트를 통과해야 한다
    p = PexelsStockProvider(api_key="dummy")
    meta = p.asset_metadata("/tmp/x.jpg", "https://pexels.com/photo/1", "홍길동")
    decision = evaluate(AssetRights.from_dict(meta))
    assert decision.usable is True
    assert decision.reasons == []


def test_enabled_with_key():
    p = PexelsStockProvider(api_key="dummy")
    assert p.enabled is True


def test_orchestrator_reports_when_stock_disabled(tmp_path):
    # 키 없이 fetch_stock=True여도 제작은 중단되지만 안내 메시지가 남아야 한다
    from app.db import get_connection, init_db
    from app.pipeline.orchestrator import produce_video

    db = tmp_path / "t.sqlite3"
    init_db(db)
    conn = get_connection(db)
    try:
        r = produce_video(
            conn, "테스트", version="A",
            work_dir=str(tmp_path / "out"),
            allow_placeholder_images=False,
            fetch_stock=True,
        )
        # 키 없음 → 스톡 보충 실패 → 소재 부족으로 중단
        assert r.ok is False
        assert any("PEXELS_API_KEY" in m for m in r.messages)
    finally:
        conn.close()
