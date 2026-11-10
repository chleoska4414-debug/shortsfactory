"""Shared JSON contract + pure parser for AI-generated micro-drama episodes.

The AI script providers (``script/openai_provider.py`` and ``script/anthropic_provider.py``)
ask a model to emit a single JSON object describing the next episode. That JSON is passed
through :func:`parse_episode_payload` below, which validates it and builds a real
:class:`~shortsfactory.story.model.Episode` (with Scene/Character/VisualSpec objects).

Keeping the parser here makes it PURE and fully offline-testable: it never touches the
network and has no SDK dependency, so the whole response->Episode path can be exercised
with a canned payload. The providers are thin network shells around this parser.

JSON CONTRACT
=============
The model must return a single JSON object (no prose, no markdown fence) of this shape::

    {
      "id": "ep02",                     # optional, defaults to a generated id
      "title": "Korean title",          # required, non-empty
      "logline": "one-line logline",    # required, non-empty
      "characters": [                   # optional; may be empty
        {
          "id": "haeun",                # required within a character
          "display_name": "서하은",      # required within a character
          "role": "female_lead",        # optional, free text
          "visual": {                   # optional; all keys optional
            "palette_top": [96, 54, 70],
            "palette_bottom": [30, 14, 24],
            "accent": [176, 40, 54],
            "skin": [244, 214, 192],
            "hair": [40, 22, 20],
            "hair_style": "long",
            "anchor_x": 0.5
          }
        }
      ],
      "scenes": [                       # required, non-empty, ordered
        {
          "index": 0,                   # optional; defaults to array order
          "beat_label": "HOOK",         # required; one of HOOK / TWIST 1 / TWIST 2 / CLIFFHANGER
          "kind": "narration",          # required; one of narration / dialog
          "text": "Korean line",        # required, non-empty
          "target_duration_sec": 4.0,    # required; within 1.0 .. 20.0
          "speaker_id": "haeun",         # optional (None => pure narration)
          "figure_id": "haeun",          # optional (defaults to speaker_id visually)
          "palette_top": [44, 52, 78],   # optional per-scene mood override
          "palette_bottom": [10, 12, 22],# optional per-scene mood override
          "rain": false,                 # optional direction flags (default false)
          "breaking_news": false,
          "emphasis": false,
          "cliffhanger": false,
          "flash": false
        }
      ]
    }

The contract intentionally mirrors the authored data in ``story/episodes.py`` so a model
prompted with that example produces something the renderer already understands.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

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

# Allowed beat labels (reuses the canonical constants from story/model.py).
_VALID_BEATS = {BEAT_HOOK, BEAT_TWIST1, BEAT_TWIST2, BEAT_CLIFFHANGER}
# Allowed scene kinds.
_VALID_KINDS = {KIND_NARRATION, KIND_DIALOG}

# Sane micro-drama per-scene duration window (seconds). Keeps a model from emitting a
# 0-second flash or a multi-minute monologue that breaks pacing.
MIN_SCENE_SEC = 1.0
MAX_SCENE_SEC = 20.0

# A compact human-readable rendering of the contract, embedded in provider prompts so the
# model knows exactly what to emit. Kept in sync with the module docstring above.
JSON_CONTRACT_PROMPT = (
    "Return ONE JSON object only (no markdown, no prose) with this shape:\n"
    '{\n'
    '  "title": "<Korean episode title>",\n'
    '  "logline": "<one-line logline>",\n'
    '  "characters": [{"id": "<id>", "display_name": "<name>", "role": "<role>"}],\n'
    '  "scenes": [{\n'
    '    "index": 0,\n'
    '    "beat_label": "HOOK|TWIST 1|TWIST 2|CLIFFHANGER",\n'
    '    "kind": "narration|dialog",\n'
    '    "speaker_id": "<character id or null>",\n'
    '    "figure_id": "<character id or null>",\n'
    '    "text": "<Korean narration or dialog>",\n'
    '    "target_duration_sec": 4.0,\n'
    '    "rain": false, "breaking_news": false, "emphasis": false,\n'
    '    "cliffhanger": false, "flash": false\n'
    '  }]\n'
    '}\n'
    "Follow the fixed four-beat spine HOOK -> TWIST 1 -> TWIST 2 -> CLIFFHANGER, keep the "
    "whole episode near 60 seconds, write Korean text, and end on a hard cliffhanger "
    "(set cliffhanger=true on the final scene)."
)


def _require(payload: Dict[str, Any], key: str, where: str) -> Any:
    if key not in payload:
        raise ValueError(f"AI episode JSON is missing required field '{key}' in {where}.")
    return payload[key]


def _non_empty_str(value: Any, key: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"AI episode JSON field '{key}' in {where} must be a non-empty string.")
    return value.strip()


def _opt_rgb(value: Any, key: str, where: str) -> Optional[Tuple[int, int, int]]:
    """Parse an optional [r, g, b] triple of ints into an RGB tuple, or None."""
    if value is None:
        return None
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 3
        or not all(isinstance(c, (int, float)) for c in value)
    ):
        raise ValueError(
            f"AI episode JSON field '{key}' in {where} must be an [r, g, b] list of three numbers."
        )
    return (int(value[0]), int(value[1]), int(value[2]))


def _bool(value: Any, key: str, where: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValueError(f"AI episode JSON field '{key}' in {where} must be true or false.")
    return value


def _parse_visual(raw: Any, where: str) -> VisualSpec:
    """Build a VisualSpec from an optional 'visual' dict, applying dataclass defaults."""
    if raw is None:
        return VisualSpec()
    if not isinstance(raw, dict):
        raise ValueError(f"AI episode JSON 'visual' in {where} must be an object.")

    spec = VisualSpec()
    top = _opt_rgb(raw.get("palette_top"), "visual.palette_top", where)
    bottom = _opt_rgb(raw.get("palette_bottom"), "visual.palette_bottom", where)
    accent = _opt_rgb(raw.get("accent"), "visual.accent", where)
    skin = _opt_rgb(raw.get("skin"), "visual.skin", where)
    hair = _opt_rgb(raw.get("hair"), "visual.hair", where)
    if top is not None:
        spec.palette_top = top
    if bottom is not None:
        spec.palette_bottom = bottom
    if accent is not None:
        spec.accent = accent
    if skin is not None:
        spec.skin = skin
    if hair is not None:
        spec.hair = hair
    if raw.get("hair_style") is not None:
        spec.hair_style = str(raw["hair_style"])
    if raw.get("anchor_x") is not None:
        try:
            spec.anchor_x = float(raw["anchor_x"])
        except (TypeError, ValueError):
            raise ValueError(f"AI episode JSON 'visual.anchor_x' in {where} must be a number.")
    if raw.get("asset_image") is not None:
        spec.asset_image = str(raw["asset_image"])
    return spec


def _parse_character(raw: Any, idx: int) -> Character:
    where = f"characters[{idx}]"
    if not isinstance(raw, dict):
        raise ValueError(f"AI episode JSON {where} must be an object.")
    cid = _non_empty_str(_require(raw, "id", where), "id", where)
    name = _non_empty_str(_require(raw, "display_name", where), "display_name", where)
    role = str(raw.get("role") or "supporting")
    visual = _parse_visual(raw.get("visual"), where)
    return Character(id=cid, display_name=name, role=role, visual=visual)


def _parse_scene(raw: Any, order: int) -> Scene:
    where = f"scenes[{order}]"
    if not isinstance(raw, dict):
        raise ValueError(f"AI episode JSON {where} must be an object.")

    beat = _non_empty_str(_require(raw, "beat_label", where), "beat_label", where)
    if beat not in _VALID_BEATS:
        allowed = ", ".join(sorted(_VALID_BEATS))
        raise ValueError(
            f"AI episode JSON {where} has unknown beat_label '{beat}'. Allowed: {allowed}."
        )

    kind = _non_empty_str(_require(raw, "kind", where), "kind", where)
    if kind not in _VALID_KINDS:
        allowed = ", ".join(sorted(_VALID_KINDS))
        raise ValueError(
            f"AI episode JSON {where} has unknown kind '{kind}'. Allowed: {allowed}."
        )

    text = _non_empty_str(_require(raw, "text", where), "text", where)

    dur_raw = _require(raw, "target_duration_sec", where)
    try:
        duration = float(dur_raw)
    except (TypeError, ValueError):
        raise ValueError(f"AI episode JSON {where} 'target_duration_sec' must be a number.")
    if not (MIN_SCENE_SEC <= duration <= MAX_SCENE_SEC):
        raise ValueError(
            f"AI episode JSON {where} 'target_duration_sec' ({duration}) is out of the "
            f"allowed {MIN_SCENE_SEC}-{MAX_SCENE_SEC}s window."
        )

    index = raw.get("index")
    if index is None:
        index = order
    else:
        try:
            index = int(index)
        except (TypeError, ValueError):
            raise ValueError(f"AI episode JSON {where} 'index' must be an integer.")

    speaker_id = raw.get("speaker_id")
    speaker_id = str(speaker_id) if speaker_id else None
    figure_id = raw.get("figure_id")
    figure_id = str(figure_id) if figure_id else None

    return Scene(
        index=index,
        beat_label=beat,
        kind=kind,
        text=text,
        target_duration_sec=duration,
        speaker_id=speaker_id,
        figure_id=figure_id,
        palette_top=_opt_rgb(raw.get("palette_top"), "palette_top", where),
        palette_bottom=_opt_rgb(raw.get("palette_bottom"), "palette_bottom", where),
        rain=_bool(raw.get("rain"), "rain", where),
        breaking_news=_bool(raw.get("breaking_news"), "breaking_news", where),
        emphasis=_bool(raw.get("emphasis"), "emphasis", where),
        cliffhanger=_bool(raw.get("cliffhanger"), "cliffhanger", where),
        flash=_bool(raw.get("flash"), "flash", where),
    )


def parse_episode_payload(payload: Dict[str, Any], default_id: str = "ai-episode") -> Episode:
    """Convert a validated AI JSON payload into an :class:`Episode`.

    This is a PURE function: no network, no SDK. It raises :class:`ValueError` with a clear,
    actionable message on malformed input (not a dict, missing required field, unknown beat
    label or kind, empty scenes, out-of-window duration).
    """
    if not isinstance(payload, dict):
        raise ValueError("AI episode JSON must be a single object at the top level.")

    title = _non_empty_str(_require(payload, "title", "episode"), "title", "episode")
    logline = _non_empty_str(_require(payload, "logline", "episode"), "logline", "episode")

    scenes_raw = payload.get("scenes")
    if not isinstance(scenes_raw, list) or not scenes_raw:
        raise ValueError("AI episode JSON must contain a non-empty 'scenes' list.")

    scenes: List[Scene] = [_parse_scene(raw, order) for order, raw in enumerate(scenes_raw)]
    # Keep scenes in the order the model emitted them, then normalize indexes so the
    # renderer always sees a clean 0..N-1 ordering.
    scenes.sort(key=lambda s: s.index)
    for i, scene in enumerate(scenes):
        scene.index = i

    chars_raw = payload.get("characters") or []
    if not isinstance(chars_raw, list):
        raise ValueError("AI episode JSON 'characters' must be a list when present.")
    characters: List[Character] = [_parse_character(raw, i) for i, raw in enumerate(chars_raw)]

    episode_id = str(payload.get("id") or default_id).strip() or default_id

    return Episode(
        id=episode_id,
        title=title,
        logline=logline,
        scenes=scenes,
        characters=characters,
    )
