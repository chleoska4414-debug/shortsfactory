"""Authored micro-drama episodes as data.

EPISODES is keyed by episode id (e.g. 'ep01'), analogous to content/topics.TOPICS. New
episodes are added here as data: define the cast (with visual specs so the offline
character renderer draws distinct, consistent figures) and the ordered scenes.

Episode 1 - 'ㅏ걷어차인 회장님' (The Chairman They Kicked Aside)
--------------------------------------------------------------
A subverted chaebol-heir x ordinary-woman romance. He is the one chasing and exposed; SHE
holds the upper hand and hides her own identity and agenda. Emotionally intense, no sexual
content, built around status reversal / hidden identity and three twists landing inside a
minute, then a hard cliffhanger.

Beats:
  HOOK (0-11s):       A rain-soaked man collapses at dawn; passersby step over him as a
                      drunk. A convenience-store clerk watches, unmoved.
  TWIST 1 (11-31s):   At her store he returns; she reveals he was not drunk - he was
                      poisoned. She knew. She is not a bystander.
  TWIST 2 (31-51s):   Breaking news names him the Daeyang Group heir. He offers her a job
                      card as thanks. She reacts with cold recognition, not awe.
  CLIFFHANGER (51-61s): She tears the card, turns away, and an old photo bearing the
                      Daeyang family crest slips from her apron. To be continued.
"""

from __future__ import annotations

from typing import Dict, List

from .model import (
    BEAT_CLIFFHANGER,
    BEAT_HOOK,
    BEAT_TWIST1,
    BEAT_TWIST2,
    KIND_DIALOG,
    KIND_NARRATION,
    Character,
    Episode,
    Scene,
    VisualSpec,
)

# --- Cast -------------------------------------------------------------------------------

# Male lead: the chaebol heir. Cool-toned corporate palette, dark swept hair, navy suit
# accent. He is the one who is exposed and chasing.
_MALE_LEAD = Character(
    id="yoojin",
    display_name="강유진",
    role="male_lead",
    visual=VisualSpec(
        palette_top=(38, 50, 92),
        palette_bottom=(12, 16, 34),
        accent=(44, 92, 170),  # navy-steel suit
        skin=(238, 208, 182),
        hair=(26, 24, 30),
        hair_style="swept",
        anchor_x=0.5,
    ),
)

# Female lead: the ordinary clerk who secretly holds the upper hand. Warm-but-muted
# palette, long dark hair, deep-crimson apron accent. Distinct from the male lead in
# palette, hair shape, placement, and wardrobe color.
_FEMALE_LEAD = Character(
    id="haeun",
    display_name="서하은",
    role="female_lead",
    visual=VisualSpec(
        palette_top=(96, 54, 70),
        palette_bottom=(30, 14, 24),
        accent=(176, 40, 54),  # crimson apron
        skin=(244, 214, 192),
        hair=(40, 22, 20),
        hair_style="long",
        anchor_x=0.5,
    ),
)

# Supporting: a news anchor for the breaking-news beat. Neutral broadcast palette.
_ANCHOR = Character(
    id="anchor",
    display_name="뉴스 속보",
    role="supporting",
    visual=VisualSpec(
        palette_top=(28, 30, 40),
        palette_bottom=(10, 11, 16),
        accent=(200, 36, 36),  # breaking-news red
        skin=(236, 206, 184),
        hair=(34, 32, 36),
        hair_style="bob",
        anchor_x=0.5,
    ),
)


def _ep01() -> Episode:
    scenes: List[Scene] = [
        # --- HOOK ---------------------------------------------------------------------
        Scene(
            index=0,
            beat_label=BEAT_HOOK,
            kind=KIND_NARRATION,
            text="새벽 네 시, 빗속에 한 남자가 쓰러졌다.",
            target_duration_sec=4.0,
            figure_id="yoojin",
            rain=True,
            palette_top=(44, 52, 78),
            palette_bottom=(10, 12, 22),
        ),
        Scene(
            index=1,
            beat_label=BEAT_HOOK,
            kind=KIND_NARRATION,
            text="사람들은 그를 술주정뱅이라 부르며 밟고 지나갔다.",
            target_duration_sec=4.0,
            figure_id="yoojin",
            rain=True,
            palette_top=(40, 46, 70),
            palette_bottom=(8, 10, 18),
        ),
        Scene(
            index=2,
            beat_label=BEAT_HOOK,
            kind=KIND_DIALOG,
            speaker_id="haeun",
            text="편의점 알바 서하은은, 그 모습을 가만히 지켜보기만 했다.",
            target_duration_sec=4.0,
            rain=True,
        ),
        # --- TWIST 1 ------------------------------------------------------------------
        Scene(
            index=3,
            beat_label=BEAT_TWIST1,
            kind=KIND_NARRATION,
            text="사흘 뒤, 그 남자가 그녀의 편의점으로 걸어 들어왔다.",
            target_duration_sec=4.0,
            figure_id="yoojin",
        ),
        Scene(
            index=4,
            beat_label=BEAT_TWIST1,
            kind=KIND_DIALOG,
            speaker_id="yoojin",
            text="그날 날 구해줘서 고맙소. 그런데… 당신은 왜 신고를 안 했지?",
            target_duration_sec=5.0,
        ),
        Scene(
            index=5,
            beat_label=BEAT_TWIST1,
            kind=KIND_DIALOG,
            speaker_id="haeun",
            text="당신은 취한 게 아니었어요. 누군가 당신을 중독시킨 거죠.",
            target_duration_sec=5.0,
            emphasis=True,
        ),
        Scene(
            index=6,
            beat_label=BEAT_TWIST1,
            kind=KIND_DIALOG,
            speaker_id="haeun",
            text="그리고 난… 처음부터 그걸 알고 있었어요.",
            target_duration_sec=5.0,
            emphasis=True,
            flash=True,
        ),
        # --- TWIST 2 ------------------------------------------------------------------
        Scene(
            index=7,
            beat_label=BEAT_TWIST2,
            kind=KIND_DIALOG,
            speaker_id="anchor",
            text="속보입니다. 대양그룹의 후계자 강유진 씨가 사흘 만에 모습을 드러냈습니다.",
            target_duration_sec=5.5,
            breaking_news=True,
        ),
        Scene(
            index=8,
            beat_label=BEAT_TWIST2,
            kind=KIND_DIALOG,
            speaker_id="yoojin",
            text="내 밑에서 일하지 않겠소? 이건 내 명함이오. 당신 정도면 뭐든 될 수 있어.",
            target_duration_sec=5.5,
        ),
        Scene(
            index=9,
            beat_label=BEAT_TWIST2,
            kind=KIND_NARRATION,
            text="하지만 하은의 눈빛엔 놀라움이 아닌, 서늘한 체념이 스쳤다.",
            target_duration_sec=6.0,
            figure_id="haeun",
            emphasis=True,
        ),
        # --- CLIFFHANGER --------------------------------------------------------------
        Scene(
            index=10,
            beat_label=BEAT_CLIFFHANGER,
            kind=KIND_DIALOG,
            speaker_id="haeun",
            text="대양그룹이라고요? …그 이름을, 내가 가장 증오하는데.",
            target_duration_sec=5.5,
            figure_id="haeun",
            emphasis=True,
            flash=True,
        ),
        Scene(
            index=11,
            beat_label=BEAT_CLIFFHANGER,
            kind=KIND_NARRATION,
            text="그녀가 명함을 찢는 순간, 앞치마에서 대양가의 문장이 박힌 낡은 사진 한 장이 떨어졌다.",
            target_duration_sec=7.0,
            figure_id="haeun",
            cliffhanger=True,
        ),
    ]

    return Episode(
        id="ep01",
        title="걷어차인 회장님",
        logline="빗속에 버려진 재벌 후계자, 그를 구한 평범한 그녀는 사실 그 가문을 무너뜨리러 왔다.",
        scenes=scenes,
        characters=[_MALE_LEAD, _FEMALE_LEAD, _ANCHOR],
    )


EPISODES: Dict[str, Episode] = {
    "ep01": _ep01(),
}


def list_episodes() -> List[str]:
    """Return the sorted ids of all available episodes."""
    return sorted(EPISODES.keys())


def get_episode(episode_id: str) -> Episode:
    """Return the Episode for ``episode_id``.

    Raises:
        KeyError: if the id is not known. The message lists valid episode ids.
    """
    key = (episode_id or "").strip().lower()
    if key not in EPISODES:
        available = ", ".join(list_episodes())
        raise KeyError(f"Unknown episode '{episode_id}'. Available episodes: {available}")
    return EPISODES[key]
