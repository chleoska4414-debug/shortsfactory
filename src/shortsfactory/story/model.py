"""Dataclasses for the scene-based micro-drama model.

Everything here is DATA-friendly (like ``content/topics.py``): an Episode is an ordered
list of Scenes plus the Characters that appear in it. A Scene references a speaker by
character id (or is narration), carries its Korean text, a beat label, a target duration,
and light direction hints the renderer can act on.

Visual identity lives on the Character via ``VisualSpec`` so the offline, code-generated
character background (``background/character.py``) can draw a distinct, deterministic,
recognizable figure that stays consistent across all of that character's scenes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Beat labels used for the standard micro-drama structure.
BEAT_HOOK = "HOOK"
BEAT_TWIST1 = "TWIST 1"
BEAT_TWIST2 = "TWIST 2"
BEAT_CLIFFHANGER = "CLIFFHANGER"

# Scene kinds.
KIND_NARRATION = "narration"
KIND_DIALOG = "dialog"

RGB = Tuple[int, int, int]


@dataclass
class VisualSpec:
    """Deterministic visual identity for a code-drawn, webtoon-style character figure.

    The fields describe a stylized vector bust: a background mood palette, an accent color
    for wardrobe, a skin tone, a hair color and a coarse hair-shape token, plus a framing
    hint. The character renderer uses these to draw a figure that is distinct per character
    and identical across that character's scenes (purely a function of this spec).
    """

    # Two-stop mood gradient for the character's default sky/background.
    palette_top: RGB = (40, 44, 72)
    palette_bottom: RGB = (16, 18, 30)
    # Wardrobe / signature accent color.
    accent: RGB = (210, 70, 70)
    skin: RGB = (236, 205, 180)
    hair: RGB = (30, 28, 34)
    # Coarse hair silhouette token: 'short', 'swept', 'long', 'bob', 'buzz'.
    hair_style: str = "short"
    # Horizontal placement of the figure within the frame, 0.0 (left) .. 1.0 (right).
    anchor_x: float = 0.5
    # Optional user/AI-supplied PNG that, if present, is composited instead of the
    # code-drawn figure. Relative to the repo root or absolute. See image_provider.py.
    asset_image: Optional[str] = None
    # Optional character-consistency controls for the OPTIONAL AI image path only. They do
    # NOT affect the offline code-drawn figure in any way. ``style_prompt`` is a stable,
    # fixed appearance description (hair, wardrobe, art style) so the generated character
    # looks the same across every scene and episode; ``seed`` is a deterministic image
    # seed combined with the prompt so repeat generations stay consistent. Both are
    # optional with defaults, so all authored data and tests are unaffected. When
    # ``style_prompt`` is None the AI path derives a stable prompt from the other fields.
    style_prompt: Optional[str] = None
    seed: int = 0


@dataclass
class Scene:
    """One directed beat of the episode."""

    index: int
    beat_label: str
    kind: str  # KIND_NARRATION or KIND_DIALOG
    text: str  # Korean narration or dialog line
    target_duration_sec: float
    # Character id of the on-screen speaker/figure; None means pure narration (no figure
    # required, though a scene may still name a figure_id to stage someone silently).
    speaker_id: Optional[str] = None
    # Which character figure to stage visually (defaults to speaker_id when not set).
    figure_id: Optional[str] = None
    # Per-scene background mood override (two-stop gradient). When None, the staged
    # character's VisualSpec palette is used.
    palette_top: Optional[RGB] = None
    palette_bottom: Optional[RGB] = None
    # Direction hints the renderer understands.
    rain: bool = False  # draw drifting rain streaks (the rainy hook)
    breaking_news: bool = False  # draw a BREAKING-NEWS lower-third band
    emphasis: bool = False  # emphasize the caption (twist punch)
    cliffhanger: bool = False  # render the emphasized cliffhanger card + teaser
    flash: bool = False  # a brief white flash in at the cut

    def staged_figure_id(self) -> Optional[str]:
        """Return the character id whose figure should be drawn for this scene."""
        return self.figure_id or self.speaker_id


@dataclass
class Character:
    """A recurring cast member with a stable visual identity."""

    id: str
    display_name: str  # Korean on-screen name label
    role: str  # 'male_lead' | 'female_lead' | 'supporting'
    visual: VisualSpec = field(default_factory=VisualSpec)


@dataclass
class Episode:
    """A full micro-drama episode authored as data."""

    id: str
    title: str  # Korean title
    logline: str  # one-line Korean/English logline
    scenes: List[Scene] = field(default_factory=list)
    characters: List[Character] = field(default_factory=list)

    @property
    def total_duration_sec(self) -> float:
        """Sum of every scene's target duration."""
        return sum(s.target_duration_sec for s in self.scenes)

    def character(self, character_id: Optional[str]) -> Optional[Character]:
        """Return the Character with ``character_id`` or None."""
        if not character_id:
            return None
        for c in self.characters:
            if c.id == character_id:
                return c
        return None
