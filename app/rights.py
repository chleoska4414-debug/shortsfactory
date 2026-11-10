"""저작권/라이선스 판정 엔진 (프로젝트 최우선 기능).

요구사항 1을 구현한다:
- CC 라이선스 종류별 상업적 이용 / 수정(2차저작) 가능 여부 판정 (1.3)
- 상업적 이용 불가 또는 미확인 소재 자동 제외 (1.2)
- 음악/초상권/상표 등 별도 권리 미확인 시 전체 사용 불가 (1.4)
- 이용 만료일 경과 시 사용 불가 (1.5)
- "출처만 표기하면 사용 가능"으로 판단하지 않음 (1.6)

이 엔진은 소재의 메타데이터만으로 사용 가능 여부(usable)와 그 사유(reasons)를 계산한다.
저작권 탐지 회피 로직은 포함하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class TriState(str, Enum):
    """권리 항목의 3-상태: 예 / 아니오 / 미확인."""

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"

    @classmethod
    def parse(cls, value) -> "TriState":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls.UNKNOWN
        v = str(value).strip().lower()
        if v in ("yes", "y", "true", "1", "가능", "허용", "o"):
            return cls.YES
        if v in ("no", "n", "false", "0", "불가", "금지", "x"):
            return cls.NO
        return cls.UNKNOWN


# CC 라이선스 매트릭스: (상업적 이용 가능, 수정/2차저작 가능, 출처표기 필요)
# 참고: Creative Commons 공식 라이선스 정의. 영상 "편집"은 2차 저작에 해당하므로
#       수정 불가(ND) 라이선스는 편집 기반 숏폼 제작에 사용할 수 없다.
CC_MATRIX: dict[str, dict] = {
    "CC0":          {"commercial": True,  "modify": True,  "attribution": False},
    "PUBLIC_DOMAIN":{"commercial": True,  "modify": True,  "attribution": False},
    "CC_BY":        {"commercial": True,  "modify": True,  "attribution": True},
    "CC_BY_SA":     {"commercial": True,  "modify": True,  "attribution": True},
    "CC_BY_NC":     {"commercial": False, "modify": True,  "attribution": True},
    "CC_BY_ND":     {"commercial": True,  "modify": False, "attribution": True},
    "CC_BY_NC_SA":  {"commercial": False, "modify": True,  "attribution": True},
    "CC_BY_NC_ND":  {"commercial": False, "modify": False, "attribution": True},
}

# 입력 정규화: 사용자가 다양한 표기로 넣어도 표준 키로 변환
_LICENSE_ALIASES: dict[str, str] = {
    "cc0": "CC0", "public domain": "PUBLIC_DOMAIN", "publicdomain": "PUBLIC_DOMAIN",
    "pd": "PUBLIC_DOMAIN",
    "cc by": "CC_BY", "cc-by": "CC_BY", "ccby": "CC_BY",
    "cc by-sa": "CC_BY_SA", "cc-by-sa": "CC_BY_SA", "ccbysa": "CC_BY_SA",
    "cc by-nc": "CC_BY_NC", "cc-by-nc": "CC_BY_NC", "ccbync": "CC_BY_NC",
    "cc by-nd": "CC_BY_ND", "cc-by-nd": "CC_BY_ND", "ccbynd": "CC_BY_ND",
    "cc by-nc-sa": "CC_BY_NC_SA", "cc-by-nc-sa": "CC_BY_NC_SA",
    "cc by-nc-nd": "CC_BY_NC_ND", "cc-by-nc-nd": "CC_BY_NC_ND",
}


def normalize_license(license_name: str | None) -> str | None:
    """라이선스 문자열을 표준 키로 정규화. 모르면 None."""
    if not license_name:
        return None
    key = str(license_name).strip().lower()
    if key in _LICENSE_ALIASES:
        return _LICENSE_ALIASES[key]
    # 이미 표준 키 형태인 경우
    upper = str(license_name).strip().upper().replace("-", "_").replace(" ", "_")
    if upper in CC_MATRIX:
        return upper
    return None


@dataclass
class AssetRights:
    """소재의 권리 메타데이터 (요구사항 1.1)."""

    license: str | None = None
    commercial_use: TriState = TriState.UNKNOWN      # 라이선스로 자동판정 보완 가능
    editable: TriState = TriState.UNKNOWN            # 수정/2차저작 가능 여부
    attribution_required: TriState = TriState.UNKNOWN
    proof_ref: str | None = None                     # 허락 증빙(파일/URL)
    expires_at: date | None = None
    # 별도 권리 항목 (요구사항 1.4)
    music_rights: TriState = TriState.UNKNOWN
    person_rights: TriState = TriState.UNKNOWN       # 인물 초상권
    trademark_rights: TriState = TriState.UNKNOWN

    @staticmethod
    def _parse_date(value) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()

    @classmethod
    def from_dict(cls, data: dict) -> "AssetRights":
        return cls(
            license=data.get("license"),
            commercial_use=TriState.parse(data.get("commercial_use")),
            editable=TriState.parse(data.get("editable")),
            attribution_required=TriState.parse(data.get("attribution_required")),
            proof_ref=data.get("proof_ref"),
            expires_at=cls._parse_date(data.get("expires_at")),
            music_rights=TriState.parse(data.get("music_rights")),
            person_rights=TriState.parse(data.get("person_rights")),
            trademark_rights=TriState.parse(data.get("trademark_rights")),
        )


@dataclass
class Decision:
    """판정 결과."""

    usable: bool
    reasons: list[str] = field(default_factory=list)
    attribution_required: bool = False
    attribution_note: str | None = None

    def as_dict(self) -> dict:
        return {
            "usable": self.usable,
            "reasons": self.reasons,
            "attribution_required": self.attribution_required,
            "attribution_note": self.attribution_note,
        }


def evaluate(rights: AssetRights, today: date | None = None) -> Decision:
    """소재의 사용 가능 여부를 판정한다.

    보수적 원칙: 하나라도 "불가" 또는 "미확인"이면 사용 불가로 처리한다.
    (요구사항 1.2, 1.4, 1.6 — 출처 표기만으로 사용 가능으로 보지 않음)
    """
    today = today or date.today()
    reasons: list[str] = []

    # 1) 라이선스 기반 자동 판정
    lic_key = normalize_license(rights.license)
    lic_commercial: TriState = rights.commercial_use
    lic_modify: TriState = rights.editable
    attribution_required = rights.attribution_required == TriState.YES

    if lic_key:
        m = CC_MATRIX[lic_key]
        # 라이선스가 명시하는 값을 신뢰. 단, 사용자가 명시적으로 NO로 덮어쓴 경우 존중.
        if rights.commercial_use == TriState.UNKNOWN:
            lic_commercial = TriState.YES if m["commercial"] else TriState.NO
        if rights.editable == TriState.UNKNOWN:
            lic_modify = TriState.YES if m["modify"] else TriState.NO
        if rights.attribution_required == TriState.UNKNOWN:
            attribution_required = m["attribution"]
    else:
        if rights.license:
            reasons.append(f"알 수 없는 라이선스 '{rights.license}' — 수동 확인 필요")
        else:
            reasons.append("라이선스 정보 없음")

    # 2) 상업적 이용 (요구사항 1.2)
    if lic_commercial == TriState.NO:
        reasons.append("상업적 이용 불가 라이선스")
    elif lic_commercial == TriState.UNKNOWN:
        reasons.append("상업적 이용 가능 여부 미확인")

    # 3) 수정/2차저작 — 영상 편집은 2차 저작 (ND 불가)
    if lic_modify == TriState.NO:
        reasons.append("수정/2차저작 불가 라이선스(편집 불가)")
    elif lic_modify == TriState.UNKNOWN:
        reasons.append("수정/편집 가능 여부 미확인")

    # 4) 별도 권리 (요구사항 1.4) — 미확인이면 전체 사용 불가
    for label, state in (
        ("음악 권리", rights.music_rights),
        ("인물 초상권", rights.person_rights),
        ("상표 권리", rights.trademark_rights),
    ):
        if state == TriState.NO:
            reasons.append(f"{label} 사용 불가")
        elif state == TriState.UNKNOWN:
            reasons.append(f"{label} 미확인")

    # 5) 만료일 (요구사항 1.5)
    if rights.expires_at is not None and rights.expires_at < today:
        reasons.append(f"이용 만료({rights.expires_at.isoformat()}) 경과")

    # 6) 출처 표기 의무가 있으면 증빙/표기 안내 (단, 표기만으로 usable 아님 — 요구사항 1.6)
    attribution_note = None
    if attribution_required:
        attribution_note = "사용 시 원저작자 출처 표기 필요"

    usable = len(reasons) == 0
    return Decision(
        usable=usable,
        reasons=reasons,
        attribution_required=attribution_required,
        attribution_note=attribution_note,
    )
