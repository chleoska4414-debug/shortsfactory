"""대본 생성 프로바이더 (요구사항 3.1, 3.7).

무료 기본 구현: 로컬 템플릿 기반 생성기 (API 키 불필요, 비용 0원).
API 키가 설정되면 LLMScriptProvider로 교체되는 구조.

중요 (요구사항 5.4, 4.2): 타인의 대본/영상 구성을 복제하지 않는다.
템플릿은 '일반적 흥행 구조'(훅→전개→반전/정리→마무리)만 제공하고,
실제 내용은 입력 주제로 채운다.

A/B 버전은 단순 길이 조절이 아니라 서로 다른 구성으로 생성한다 (요구사항 3.7):
- A (25~45초): 단일 핵심 메시지, 빠른 훅, 1~2개 포인트, 즉각 마무리
- B (65~90초): 맥락 도입, 3~4개 포인트 전개, 반전/심화, 정리 마무리
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ScriptSegment:
    """대본의 한 구간 — 내레이션 문장과 화면 지시."""

    role: str          # hook | point | twist | outro
    narration: str
    scene_hint: str    # 이 구간에 어울리는 화면 소재 힌트(키워드)


@dataclass
class Script:
    version: str                 # A | B
    topic: str
    tone: str
    title: str
    description: str
    hashtags: list[str]
    thumbnail_text: str
    segments: list[ScriptSegment] = field(default_factory=list)
    provider: str = ""

    @property
    def full_narration(self) -> str:
        return " ".join(s.narration for s in self.segments)


class ScriptProvider(Protocol):
    def generate(self, topic: str, version: str, tone: str = "info") -> Script:
        ...


class TemplateScriptProvider:
    """무료 로컬 템플릿 대본 생성기.

    흥행 '구조'만 차용하고 내용은 주제로 채운다(복제 금지).
    고품질 대본이 필요하면 .env에 LLM 키를 설정해 LLM 프로바이더로 교체한다.
    """

    name = "template(free)"

    def generate(self, topic: str, version: str, tone: str = "info") -> Script:
        topic = topic.strip()
        version = version.upper()
        if version == "A":
            return self._short(topic, tone)
        return self._long(topic, tone)

    def _short(self, topic: str, tone: str) -> Script:
        """A: 25~45초 — 짧고 강렬, 단일 메시지.

        세그먼트당 1~2문장으로 구성해 약 25~45초를 채운다.
        B와 달리 맥락 설명 없이 하나의 핵심 메시지로 빠르게 몰아간다.
        """
        segments = [
            ScriptSegment(
                "hook",
                f"혹시 {topic}, 제대로 알고 계셨나요? "
                f"대부분은 중요한 한 가지를 놓치고 있습니다.",
                f"{topic} 대표 이미지",
            ),
            ScriptSegment(
                "point",
                f"{topic}에서 가장 많이 놓치는 핵심은 바로 이것입니다. "
                f"작은 차이 같지만 결과를 완전히 바꿉니다.",
                f"{topic} 핵심 장면",
            ),
            ScriptSegment(
                "twist",
                "사실 복잡하게 생각할 필요 없이, 이 한 가지만 기억하면 충분합니다. "
                "오늘부터 바로 적용해 보세요.",
                f"{topic} 강조 장면",
            ),
            ScriptSegment(
                "outro",
                "도움이 되셨다면 팔로우하고 다음 편도 확인해 주세요.",
                "마무리 그래픽",
            ),
        ]
        return Script(
            version="A",
            topic=topic,
            tone=tone,
            title=f"{topic}, 30초 요약",
            description=f"{topic}의 핵심만 빠르게 정리했습니다.",
            hashtags=self._hashtags(topic),
            thumbnail_text=f"{topic}\n핵심 요약",
            segments=segments,
            provider=self.name,
        )

    def _long(self, topic: str, tone: str) -> Script:
        """B: 65~90초 — 완결성, 맥락→전개→심화→정리.

        각 세그먼트를 2~3문장으로 구성해 목표 길이(약 65~90초)를 채운다.
        A 버전과 달리 맥락 설명과 근거가 추가된 완결형 구성이다.
        """
        segments = [
            ScriptSegment(
                "hook",
                f"{topic}, 왜 요즘 이렇게 자주 이야기되는지 궁금하셨나요? "
                f"많은 분들이 대충 알고 넘어가지만, 핵심을 놓치면 오히려 손해일 수 있습니다. "
                f"끝까지 보시면 {topic}의 전체 그림이 깔끔하게 정리됩니다.",
                f"{topic} 도입 이미지",
            ),
            ScriptSegment(
                "point",
                f"먼저 {topic}의 배경부터 간단히 짚어보겠습니다. "
                f"처음에는 작은 관심에서 시작했지만, 점점 많은 사람들의 일상에 자리 잡게 되었습니다. "
                f"그 흐름을 알면 왜 지금 중요한지 이해가 쉬워집니다.",
                f"{topic} 배경 장면",
            ),
            ScriptSegment(
                "point",
                "그런데 여기서 많은 분들이 오해하는 부분이 하나 있습니다. "
                "흔히 알려진 방법이 늘 정답은 아니라는 점입니다. "
                "상황에 따라 전혀 다른 접근이 필요할 때가 많습니다.",
                f"{topic} 비교 장면",
            ),
            ScriptSegment(
                "twist",
                "하지만 실제 데이터를 들여다보면 이야기가 조금 달라집니다. "
                "우리가 당연하게 여겼던 것과 정반대의 결과가 나오는 경우도 있습니다. "
                "바로 이 지점이 대부분이 놓치는 핵심입니다.",
                f"{topic} 반전 장면",
            ),
            ScriptSegment(
                "point",
                "그래서 실제로 활용할 때는 이 순서로 접근하는 것이 좋습니다. "
                "먼저 목표를 분명히 하고, 그다음 자신의 상황에 맞게 조정하는 것입니다. "
                "이렇게만 해도 결과가 눈에 띄게 달라집니다.",
                f"{topic} 활용 장면",
            ),
            ScriptSegment(
                "outro",
                "오늘 내용이 도움이 되셨다면 저장해 두고 필요할 때 다시 꺼내 보세요. "
                "팔로우해 두시면 다음 편도 놓치지 않고 받아보실 수 있습니다.",
                "마무리 그래픽",
            ),
        ]
        return Script(
            version="B",
            topic=topic,
            tone=tone,
            title=f"{topic} 완벽 정리 (1분 버전)",
            description=f"{topic}에 대해 배경부터 활용까지 한 번에 정리했습니다.",
            hashtags=self._hashtags(topic),
            thumbnail_text=f"{topic}\n완벽 정리",
            segments=segments,
            provider=self.name,
        )

    @staticmethod
    def _hashtags(topic: str) -> list[str]:
        base = ["#쇼츠", "#릴스", "#숏폼", "#정보"]
        kw = topic.replace(" ", "")
        return [f"#{kw}"] + base


def get_script_provider() -> ScriptProvider:
    from app.config import get_settings

    settings = get_settings()
    # 향후: if settings.llm_provider == "api" and settings.openai_api_key: return LLMScriptProvider(...)
    return TemplateScriptProvider()
