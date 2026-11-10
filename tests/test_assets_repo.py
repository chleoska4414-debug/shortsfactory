"""소재 저장소 + DB 통합 테스트 (Task 3).

권리 판정이 등록 시 자동 적용되고, 사용 불가 소재가 선택에서 제외되는지 검증.
임시 SQLite 파일을 사용한다.
"""

from datetime import date, timedelta

import pytest

from app.assets_repo import (
    create_asset,
    list_assets,
    select_usable_assets,
)
from app.db import get_connection, init_db


@pytest.fixture()
def conn(tmp_path):
    db = tmp_path / "test.sqlite3"
    init_db(db)
    c = get_connection(db)
    yield c
    c.close()


def test_usable_asset_registered_and_selectable(conn):
    a = create_asset(conn, {
        "type": "video", "title": "맑은 하늘 타임랩스", "license": "CC0",
        "music_rights": "yes", "person_rights": "yes", "trademark_rights": "yes",
    })
    assert a["usable"] is True
    assert a["reasons"] == []
    selectable = select_usable_assets(conn, asset_type="video")
    assert any(x["id"] == a["id"] for x in selectable)


def test_unknown_rights_asset_excluded_from_selection(conn):
    # 음악 권리 미확인 → 사용 불가 → 선택에서 제외 (요구사항 1.4, 2.3)
    a = create_asset(conn, {
        "type": "video", "title": "출처불명 영상", "license": "CC0",
        # music_rights 미지정 → unknown
    })
    assert a["usable"] is False
    assert len(a["reasons"]) > 0
    selectable = select_usable_assets(conn, asset_type="video")
    assert all(x["id"] != a["id"] for x in selectable)


def test_nc_license_excluded(conn):
    a = create_asset(conn, {
        "type": "image", "title": "NC 이미지", "license": "CC BY-NC",
        "music_rights": "yes", "person_rights": "yes", "trademark_rights": "yes",
    })
    assert a["usable"] is False
    assert any("상업적 이용 불가" in r for r in a["reasons"])


def test_expired_asset_excluded_at_selection_time(conn):
    # 등록은 되지만 만료되어 사용 불가
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    a = create_asset(conn, {
        "type": "music", "title": "만료된 음원", "license": "CC0",
        "music_rights": "yes", "person_rights": "yes", "trademark_rights": "yes",
        "expires_at": yesterday,
    })
    assert a["usable"] is False
    selectable = select_usable_assets(conn, asset_type="music")
    assert all(x["id"] != a["id"] for x in selectable)


def test_list_filters_by_type(conn):
    create_asset(conn, {"type": "video", "license": "CC0",
                        "music_rights": "yes", "person_rights": "yes", "trademark_rights": "yes"})
    create_asset(conn, {"type": "image", "license": "CC0",
                        "music_rights": "yes", "person_rights": "yes", "trademark_rights": "yes"})
    videos = list_assets(conn, asset_type="video")
    images = list_assets(conn, asset_type="image")
    assert len(videos) == 1
    assert len(images) == 1
