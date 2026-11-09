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
    """Protocol every script provider implements."""

    def generate(self, topic: str, n_cards: int) -> Script:
        """Build a Script for the given topic using up to n_cards content cards."""
        ...
