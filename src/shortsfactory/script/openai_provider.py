"""Optional network AI script provider using OpenAI (GPT).

NOT exercised by the offline test suite's network path. It lazily imports the ``openai``
SDK inside the call, requires an OPENAI_API_KEY, and raises a clear, actionable
RuntimeError if the key, the dependency, or the network is missing. On success it asks the
model for the shared JSON episode contract and passes the response through the pure parser
in ``story.ai_parser`` to return an :class:`~shortsfactory.story.model.Episode`.

This is the EPISODE path (``generate_episode``), distinct from the knowledge-card
``ScriptProvider.generate(topic, n_cards)`` protocol. The offline 'template' provider still
owns the card path and remains the default.
"""

from __future__ import annotations

from typing import Optional

from ..story.model import Episode
from .ai_base import _SYSTEM_PROMPT, build_user_prompt, parse_model_json

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIScriptProvider:
    """Generate the next micro-drama Episode with an OpenAI chat model.

    Requires the ``openai`` package and an OPENAI_API_KEY plus outbound internet.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL

    def generate_episode(self, bible: str, previous_cliffhanger: str = "") -> Episode:
        if not self.api_key:
            raise RuntimeError(
                "The 'openai' script provider requires an OpenAI API key. "
                "Set OPENAI_API_KEY in your .env (get a key at https://platform.openai.com/). "
                "This provider also needs outbound internet access to OpenAI servers. "
                "Use the offline 'template' default (no --provider-script) to generate without a key."
            )
        try:
            from openai import OpenAI  # lazy import
        except Exception as exc:  # pragma: no cover - network provider
            raise RuntimeError(
                "The 'openai' script provider requires the openai package. "
                "Install it with: pip install 'shortsfactory[providers]'  (or: pip install openai). "
                "Use the offline 'template' default to generate without it."
            ) from exc

        try:  # pragma: no cover - network provider
            client = OpenAI(api_key=self.api_key)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(bible, previous_cliffhanger)},
                ],
                response_format={"type": "json_object"},
                temperature=0.9,
            )
            raw_text = resp.choices[0].message.content
        except Exception as exc:  # pragma: no cover - network provider
            raise RuntimeError(
                "OpenAI script generation failed. This provider needs outbound internet "
                "access to OpenAI servers, which is not available in offline environments. "
                "Use the offline 'template' default (no --provider-script) for a fully offline run. "
                f"Underlying error: {exc}"
            ) from exc

        # The parser is PURE and offline-testable; it raises ValueError on malformed JSON.
        return parse_model_json(raw_text)
