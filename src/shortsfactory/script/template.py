"""Offline, deterministic template-based script provider.

TemplateScriptProvider builds a short 25-45 second narration from a content pack:
an intro hook, N fact segments, and an outro call-to-action. It performs NO network
calls, making it the guaranteed-available default.
"""

from __future__ import annotations

from ..content.topics import get_topic
from .base import Script, Segment, estimate_duration


class TemplateScriptProvider:
    """Builds a narration script from a data-driven topic pack."""

    def generate(self, topic: str, n_cards: int = 5) -> Script:
        cards = get_topic(topic)
        n = max(1, min(int(n_cards), len(cards)))
        chosen = cards[:n]

        segments = []

        intro = f"Here are {n} mind-blowing facts about {topic} that you probably didn't know."
        segments.append(Segment(text=intro, est_duration_sec=estimate_duration(intro)))

        for card in chosen:
            headline = card.get("headline", "").strip()
            fact = card.get("fact", "").strip()
            if headline:
                text = f"{headline}. {fact}"
            else:
                text = fact
            segments.append(Segment(text=text, est_duration_sec=estimate_duration(text)))

        outro = "If that surprised you, follow for more and share it with a friend."
        segments.append(Segment(text=outro, est_duration_sec=estimate_duration(outro)))

        return Script(topic=topic, segments=segments)
