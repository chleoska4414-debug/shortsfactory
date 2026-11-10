"""저작권 판정 엔진 단위 테스트 (Task 2.4).

요구사항 1의 수용 기준을 검증한다. 보수적 판정(미확인=불가)을 핵심으로 확인한다.
"""

from datetime import date, timedelta

import pytest

from app.rights import (
    AssetRights,
    TriState,
    evaluate,
    normalize_license,
)


def _full_ok(**overrides):
    """모든 별도 권리가 확인된, 기본적으로 사용 가능한 소재를 만든다."""
    base = dict(
        license="CC0",
        music_rights="yes",
        person_rights="yes",
        trademark_rights="yes",
    )
    base.update(overrides)
    return AssetRights.from_dict(base)


# ---------- 라이선스 정규화 ----------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("CC0", "CC0"),
        ("cc by", "CC_BY"),
        ("CC BY-NC", "CC_BY_NC"),
        ("cc-by-nd", "CC_BY_ND"),
        ("public domain", "PUBLIC_DOMAIN"),
        ("듣보잡라이선스", None),
        (None, None),
    ],
)
def test_normalize_license(raw, expected):
    assert normalize_license(raw) == expected


# ---------- CC 종류별 상업/수정 판정 (요구사항 1.3) ----------

def test_cc0_usable():
    d = evaluate(_full_ok(license="CC0"))
    assert d.usable is True
    assert d.reasons == []


def test_cc_by_usable_with_attribution():
    d = evaluate(_full_ok(license="CC BY"))
    assert d.usable is True
    assert d.attribution_required is True
    assert "출처 표기" in (d.attribution_note or "")


def test_cc_by_nc_blocks_commercial():
    # NC = 상업적 이용 불가 → 사용 불가 (요구사항 1.2)
    d = evaluate(_full_ok(license="CC BY-NC"))
    assert d.usable is False
    assert any("상업적 이용 불가" in r for r in d.reasons)


def test_cc_by_nd_blocks_editing():
    # ND = 수정 불가 → 영상 편집(2차저작) 불가 → 사용 불가
    d = evaluate(_full_ok(license="CC BY-ND"))
    assert d.usable is False
    assert any("편집 불가" in r for r in d.reasons)


def test_cc_by_nc_nd_blocks_both():
    d = evaluate(_full_ok(license="CC BY-NC-ND"))
    assert d.usable is False
    assert any("상업적 이용 불가" in r for r in d.reasons)
    assert any("편집 불가" in r for r in d.reasons)


# ---------- 미확인 처리 (요구사항 1.2, 1.4, 1.6) ----------

def test_unknown_license_not_usable():
    d = evaluate(_full_ok(license=None))
    assert d.usable is False
    assert any("라이선스 정보 없음" in r for r in d.reasons)


def test_unknown_music_rights_blocks_whole_asset():
    d = evaluate(_full_ok(license="CC0", music_rights="unknown"))
    assert d.usable is False
    assert any("음악 권리 미확인" in r for r in d.reasons)


def test_unknown_person_rights_blocks():
    d = evaluate(_full_ok(license="CC0", person_rights="unknown"))
    assert d.usable is False
    assert any("인물 초상권 미확인" in r for r in d.reasons)


def test_attribution_alone_does_not_make_usable():
    # 요구사항 1.6: 출처 표기 의무만 있고 다른 권리가 미확인이면 사용 불가
    d = evaluate(
        AssetRights.from_dict(
            dict(license="CC BY", attribution_required="yes")
            # music/person/trademark 미확인 상태
        )
    )
    assert d.usable is False


# ---------- 만료일 (요구사항 1.5) ----------

def test_expired_asset_not_usable():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    d = evaluate(_full_ok(license="CC0", expires_at=yesterday))
    assert d.usable is False
    assert any("만료" in r for r in d.reasons)


def test_future_expiry_ok():
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    d = evaluate(_full_ok(license="CC0", expires_at=tomorrow))
    assert d.usable is True


# ---------- 사용자 명시 override ----------

def test_explicit_commercial_no_overrides_permissive_license():
    # CC0는 상업 가능이지만 사용자가 commercial_use=no로 명시하면 불가
    d = evaluate(_full_ok(license="CC0", commercial_use="no"))
    assert d.usable is False


def test_tristate_parse_korean():
    assert TriState.parse("가능") == TriState.YES
    assert TriState.parse("불가") == TriState.NO
    assert TriState.parse("") == TriState.UNKNOWN
