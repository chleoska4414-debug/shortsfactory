"""Script provider abstraction.

A ScriptProvider turns a topic name into a narration Script: an ordered list of segments.
Each segment carries the spoken/displayed text and an estimated duration in seconds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Protocol, runtime_checkable

# Narration pacing used to estimate durations when a provider has no better signal.
WORDS_PER_SECOND = 2.8
MIN_SEGMENT_SEC = 2.0


@dataclass
class Segment:
    """A single spoken/displayed unit of the script."""

    text: str
    est_duration_sec: float


@dataclass
class Script:
    """An ordered narration script for one short video."""

    topic: str
    segments: List[Segment] = field(default_factory=list)

    @property
    def text(self) -> str:
        """The full narration joined into one string."""
        return " ".join(s.text for s in self.segments)

    @property
    def total_duration_sec(self) -> float:
        """Sum of every segment's estimated duration."""
        return sum(s.est_duration_sec for s in self.segments)


def estimate_duration(text: str) -> float:
    """Estimate narration duration for a chunk of text, clamped to a sane minimum."""
    words = len((text or "").split())
    return max(MIN_SEGMENT_SEC, round(words / WORDS_PER_SECOND, 2))


@runtime_checkable
class ScriptProvider(Protocol):
    """Protocol every script provider implements.

    This is the KNOWLEDGE-CARD path: a topic name plus a card budget becomes a narration
    :class:`Script` (a flat list of :class:`Segment`). The offline 'template' provider and
    the knowledge-card pipeline use this path exclusively.
    """

    def generate(self, topic: str, n_cards: int) -> Script:
        """Build a Script for the given topic using up to n_cards content cards."""
        ...


@runtime_checkable
class EpisodeGenerator(Protocol):
    """Protocol for providers that generate a micro-drama :class:`Episode`.

    This is a SEPARATE path from :class:`ScriptProvider`. Knowledge-card providers return a
    flat narration ``Script``; AI drama providers (OpenAI/Anthropic) instead return a full
    scene-based ``Episode`` (parsed into Episode/Scene/Character via
    ``story.ai_parser``). The two paths are deliberately distinct so the card protocol and
    the offline 'template' card path are never broken: an AI provider implements
    ``generate_episode`` and is selected only on the episode render path.

    ``Episode`` is intentionally not imported here to keep this base module free of a
    story-package dependency; it is referenced structurally.
    """

    def generate_episode(self, bible: str, previous_cliffhanger: str):
        """Generate the next Episode from the series ``bible`` text and the prior
        episode's ``previous_cliffhanger`` summary. Returns a ``story.model.Episode``."""
        ...
