"""Offline tests for the AI script/story providers (OpenAI + Anthropic).

These tests NEVER make a network call. They verify:
  (a) factory registration + resolution of 'openai' and 'anthropic';
  (b) the key-missing error path raises a RuntimeError naming the env var;
  (c) the pure JSON->Episode parser builds a valid Episode and rejects malformed input;
  (d) a stubbed/monkeypatched SDK client returns canned JSON and the provider parses it
      into an Episode with no real network.
"""

from __future__ import annotations

import copy

import pytest

from shortsfactory.script import available_script_providers, get_script_provider
from shortsfactory.script.anthropic_provider import AnthropicScriptProvider
from shortsfactory.script.openai_provider import OpenAIScriptProvider
from shortsfactory.story.ai_parser import (
    MAX_SCENE_SEC,
    MIN_SCENE_SEC,
    parse_episode_payload,
)
from shortsfactory.story.model import (
    BEAT_CLIFFHANGER,
    BEAT_HOOK,
    KIND_DIALOG,
    KIND_NARRATION,
    Episode,
)


# --- Representative sample payload (what a model should emit) ---------------------------

def _sample_payload():
    return {
        "id": "ep02",
        "title": "돌아온 그 이름",
        "logline": "하은이 찢어버린 명함, 그리고 떨어진 사진 한 장의 비밀.",
        "characters": [
            {
                "id": "haeun",
                "display_name": "서하은",
                "role": "female_lead",
                "visual": {
                    "palette_top": [96, 54, 70],
                    "palette_bottom": [30, 14, 24],
                    "accent": [176, 40, 54],
                    "hair_style": "long",
                    "anchor_x": 0.5,
                },
            },
            {"id": "yoojin", "display_name": "강유진", "role": "male_lead"},
        ],
        "scenes": [
            {
                "index": 0,
                "beat_label": "HOOK",
                "kind": "narration",
                "text": "그녀는 사진을 주워 들고 한참을 바라보았다.",
                "target_duration_sec": 4.0,
                "figure_id": "haeun",
                "rain": True,
            },
            {
                "index": 1,
                "beat_label": "TWIST 1",
                "kind": "dialog",
                "speaker_id": "yoojin",
                "text": "그 사진, 어디서 났지?",
                "target_duration_sec": 5.0,
                "emphasis": True,
            },
            {
                "index": 2,
                "beat_label": "TWIST 2",
                "kind": "dialog",
                "speaker_id": "haeun",
                "text": "당신 아버지가, 내 아버지를 죽였어요.",
                "target_duration_sec": 5.5,
                "emphasis": True,
                "flash": True,
            },
            {
                "index": 3,
                "beat_label": "CLIFFHANGER",
                "kind": "narration",
                "text": "하은은 품에서 또 다른 사진을 꺼냈다. 다음 화에 계속.",
                "target_duration_sec": 6.0,
                "figure_id": "haeun",
                "cliffhanger": True,
            },
        ],
    }


# --- (a) registration + resolution ------------------------------------------------------

def test_factory_registers_ai_providers():
    names = available_script_providers()
    assert "template" in names  # offline default stays registered
    assert "openai" in names
    assert "anthropic" in names


def test_factory_resolves_ai_providers(monkeypatch):
    # Keys present so construction succeeds; no call is made, so no network.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert isinstance(get_script_provider("openai"), OpenAIScriptProvider)
    assert isinstance(get_script_provider("anthropic"), AnthropicScriptProvider)


# --- (b) key-missing error path ---------------------------------------------------------

def test_openai_missing_key_raises_runtimeerror(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = get_script_provider("openai")
    with pytest.raises(RuntimeError) as exc:
        provider.generate_episode("bible", "prev cliffhanger")
    assert "OPENAI_API_KEY" in str(exc.value)
    assert "template" in str(exc.value)  # points to the offline default


def test_anthropic_missing_key_raises_runtimeerror(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = get_script_provider("anthropic")
    with pytest.raises(RuntimeError) as exc:
        provider.generate_episode("bible", "prev cliffhanger")
    assert "ANTHROPIC_API_KEY" in str(exc.value)
    assert "template" in str(exc.value)


# --- (c) pure parser: happy path --------------------------------------------------------

def test_parser_builds_valid_episode():
    episode = parse_episode_payload(_sample_payload())
    assert isinstance(episode, Episode)
    assert episode.id == "ep02"
    assert episode.title and episode.logline

    # Scenes ordered 0..N-1.
    assert [s.index for s in episode.scenes] == [0, 1, 2, 3]

    # Beats and kinds mapped.
    assert episode.scenes[0].beat_label == BEAT_HOOK
    assert episode.scenes[0].kind == KIND_NARRATION
    assert episode.scenes[1].kind == KIND_DIALOG
    assert episode.scenes[-1].beat_label == BEAT_CLIFFHANGER

    # Cliffhanger flag set on the final scene.
    assert episode.scenes[-1].cliffhanger is True

    # Durations within the micro-drama window.
    for s in episode.scenes:
        assert MIN_SCENE_SEC <= s.target_duration_sec <= MAX_SCENE_SEC

    # Characters parsed with visual spec overrides.
    haeun = episode.character("haeun")
    assert haeun is not None
    assert haeun.display_name == "서하은"
    assert haeun.visual.hair_style == "long"
    assert haeun.visual.accent == (176, 40, 54)


def test_parser_normalizes_out_of_order_scenes():
    payload = _sample_payload()
    payload["scenes"].reverse()  # emit scenes out of order
    episode = parse_episode_payload(payload)
    assert [s.index for s in episode.scenes] == [0, 1, 2, 3]
    assert episode.scenes[0].beat_label == BEAT_HOOK
    assert episode.scenes[-1].beat_label == BEAT_CLIFFHANGER


# --- (c) pure parser: malformed input ---------------------------------------------------

def test_parser_rejects_non_dict():
    with pytest.raises(ValueError):
        parse_episode_payload(["not", "a", "dict"])  # type: ignore[arg-type]


def test_parser_rejects_empty_scenes():
    payload = _sample_payload()
    payload["scenes"] = []
    with pytest.raises(ValueError) as exc:
        parse_episode_payload(payload)
    assert "scenes" in str(exc.value)


def test_parser_rejects_missing_title():
    payload = _sample_payload()
    del payload["title"]
    with pytest.raises(ValueError) as exc:
        parse_episode_payload(payload)
    assert "title" in str(exc.value)


def test_parser_rejects_unknown_beat():
    payload = _sample_payload()
    payload["scenes"][0]["beat_label"] = "INTRO"
    with pytest.raises(ValueError) as exc:
        parse_episode_payload(payload)
    assert "beat_label" in str(exc.value)


def test_parser_rejects_unknown_kind():
    payload = _sample_payload()
    payload["scenes"][0]["kind"] = "song"
    with pytest.raises(ValueError) as exc:
        parse_episode_payload(payload)
    assert "kind" in str(exc.value)


def test_parser_rejects_missing_text():
    payload = _sample_payload()
    del payload["scenes"][0]["text"]
    with pytest.raises(ValueError):
        parse_episode_payload(payload)


def test_parser_rejects_out_of_window_duration():
    payload = _sample_payload()
    payload["scenes"][0]["target_duration_sec"] = 120.0
    with pytest.raises(ValueError) as exc:
        parse_episode_payload(payload)
    assert "target_duration_sec" in str(exc.value)


# --- (d) stubbed SDK clients (no network) -----------------------------------------------

import json as _json


class _FakeOpenAIResponse:
    def __init__(self, text):
        self.choices = [
            type("C", (), {"message": type("M", (), {"content": text})()})()
        ]


class _FakeOpenAIClient:
    def __init__(self, *args, **kwargs):
        # The canned JSON the "model" returns.
        self._text = _json.dumps(_sample_payload())
        self.chat = type(
            "Chat",
            (),
            {"completions": type("Comp", (), {"create": self._create})()},
        )()

    def _create(self, *args, **kwargs):
        return _FakeOpenAIResponse(self._text)


class _FakeOpenAIModule:
    OpenAI = _FakeOpenAIClient


def test_openai_provider_parses_stubbed_client(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "openai", _FakeOpenAIModule)
    provider = OpenAIScriptProvider(api_key="sk-test")
    episode = provider.generate_episode("bible text", "prior cliffhanger")
    assert isinstance(episode, Episode)
    assert episode.scenes[-1].beat_label == BEAT_CLIFFHANGER
    assert episode.scenes[-1].cliffhanger is True


class _FakeAnthropicResponse:
    def __init__(self, text):
        self.content = [type("Block", (), {"text": text})()]


class _FakeAnthropicClient:
    def __init__(self, *args, **kwargs):
        self._text = _json.dumps(_sample_payload())
        self.messages = type("Messages", (), {"create": self._create})()

    def _create(self, *args, **kwargs):
        return _FakeAnthropicResponse(self._text)


class _FakeAnthropicModule:
    Anthropic = _FakeAnthropicClient


def test_anthropic_provider_parses_stubbed_client(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "anthropic", _FakeAnthropicModule)
    provider = AnthropicScriptProvider(api_key="sk-ant-test")
    episode = provider.generate_episode("bible text", "prior cliffhanger")
    assert isinstance(episode, Episode)
    assert episode.scenes[0].beat_label == BEAT_HOOK


def test_provider_handles_fenced_json(monkeypatch):
    """A model that wraps JSON in a ```json fence is still parsed."""
    import sys

    fenced = "```json\n" + _json.dumps(_sample_payload()) + "\n```"

    class _FencedClient(_FakeOpenAIClient):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._text = fenced

    monkeypatch.setitem(
        sys.modules, "openai", type("M", (), {"OpenAI": _FencedClient})
    )
    provider = OpenAIScriptProvider(api_key="sk-test")
    episode = provider.generate_episode("b", "c")
    assert isinstance(episode, Episode)
