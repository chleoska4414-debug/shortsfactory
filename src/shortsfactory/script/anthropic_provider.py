"""Optional network AI script provider using Anthropic (Claude).

NOT exercised by the offline test suite's network path. It lazily imports the
``anthropic`` SDK inside the call, requires an ANTHROPIC_API_KEY, and raises a clear,
actionable RuntimeError if the key, the dependency, or the network is missing. On success
it asks the model for the shared JSON episode contract and passes the response through the
pure parser in ``story.ai_parser`` to return an :class:`~shortsfactory.story.model.Episode`.

This is the EPISODE path (``generate_episode``), distinct from the knowledge-card
``ScriptProvider.generate(topic, n_cards)`` protocol. The offline 'template' provider still
owns the card path and remains the default.
"""

from __future__ import annotations

from typing import Optional

from ..story.model import Episode
from .ai_base import _SYSTEM_PROMPT, build_user_prompt, parse_model_json

DEFAULT_MODEL = "claude-3-5-sonnet-latest"


class AnthropicScriptProvider:
    """Generate the next micro-drama Episode with an Anthropic Claude model.

    Requires the ``anthropic`` package and an ANTHROPIC_API_KEY plus outbound internet.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL

    def generate_episode(self, bible: str, previous_cliffhanger: str = "") -> Episode:
        if not self.api_key:
            raise RuntimeError(
                "The 'anthropic' script provider requires an Anthropic API key. "
                "Set ANTHROPIC_API_KEY in your .env (get a key at https://console.anthropic.com/). "
                "This provider also needs outbound internet access to Anthropic servers. "
                "Use the offline 'template' default (no --provider-script) to generate without a key."
            )
        try:
            import anthropic  # lazy import
        except Exception as exc:  # pragma: no cover - network provider
            raise RuntimeError(
                "The 'anthropic' script provider requires the anthropic package. "
                "Install it with: pip install 'shortsfactory[providers]'  (or: pip install anthropic). "
                "Use the offline 'template' default to generate without it."
            ) from exc

        try:  # pragma: no cover - network provider
            client = anthropic.Anthropic(api_key=self.api_key)
            resp = client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0.9,
                system=_SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": build_user_prompt(bible, previous_cliffhanger)},
                ],
            )
            raw_text = resp.content[0].text
        except Exception as exc:  # pragma: no cover - network provider
            raise RuntimeError(
                "Anthropic script generation failed. This provider needs outbound internet "
                "access to Anthropic servers, which is not available in offline environments. "
                "Use the offline 'template' default (no --provider-script) for a fully offline run. "
                f"Underlying error: {exc}"
            ) from exc

        # The parser is PURE and offline-testable; it raises ValueError on malformed JSON.
        return parse_model_json(raw_text)
