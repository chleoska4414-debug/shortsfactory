"""Shared scaffolding for the network AI episode-generation providers.

Both the OpenAI (GPT) and Anthropic (Claude) providers follow the same shape as the other
network providers in this project (``tts/edge.py``, ``background/pexels.py``):

* lazy-import the SDK inside the call (never at module import time, so the registry and the
  offline suite work whether or not the SDK is installed),
* gate on an API key and raise a clear, actionable RuntimeError that names the env var,
  says outbound internet is required, and points to the offline 'template' default,
* pass the model's JSON response through the shared, PURE parser in
  ``story.ai_parser`` to return a real :class:`~shortsfactory.story.model.Episode`.

These providers implement ``generate_episode(bible, previous_cliffhanger) -> Episode``,
the episode path (NOT the knowledge-card ``generate(topic, n_cards) -> Script`` protocol).
"""

from __future__ import annotations

import json
from typing import Optional

from ..story.ai_parser import JSON_CONTRACT_PROMPT, parse_episode_payload
from ..story.model import Episode

_SYSTEM_PROMPT = (
    "You are a story writer for a vertical Korean micro-drama (short-drama). Given the "
    "series bible and the previous episode's cliffhanger, you write the NEXT episode. You "
    "respond with a single JSON object and nothing else."
)


def build_user_prompt(bible: str, previous_cliffhanger: str) -> str:
    """Compose the user prompt from the series bible + the prior cliffhanger + the contract.

    Pure string assembly, so it is offline-testable and shared by both providers.
    """
    bible = (bible or "").strip()
    previous_cliffhanger = (previous_cliffhanger or "").strip() or "(none; this is the first episode)"
    return (
        "SERIES BIBLE:\n"
        f"{bible}\n\n"
        "PREVIOUS EPISODE CLIFFHANGER / SUMMARY:\n"
        f"{previous_cliffhanger}\n\n"
        "Write the next episode that pays off the cliffhanger and ends on a new one.\n\n"
        f"{JSON_CONTRACT_PROMPT}"
    )


def parse_model_json(raw_text: str) -> Episode:
    """Parse a model's raw text response (expected JSON) into an Episode.

    Tolerates a stray ```json fenced block by stripping fences before decoding. Raises
    ValueError (consistent with the parser) when the response is not valid JSON.
    """
    text = (raw_text or "").strip()
    if text.startswith("```"):
        # Strip a leading ```json / ``` fence and the trailing fence if present.
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        payload = json.loads(text)
    except Exception as exc:
        raise ValueError(
            f"AI episode response was not valid JSON matching the contract. Underlying error: {exc}"
        ) from exc
    return parse_episode_payload(payload)
