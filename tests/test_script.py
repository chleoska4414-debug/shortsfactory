"""Tests for the offline template script provider."""

from __future__ import annotations

from shortsfactory.script import TemplateScriptProvider, get_script_provider
from shortsfactory.script.base import Script


def test_template_generates_intro_facts_outro():
    provider = TemplateScriptProvider()
    script = provider.generate("space", n_cards=3)

    assert isinstance(script, Script)
    # intro + 3 facts + outro
    assert len(script.segments) == 5
    assert all(seg.text.strip() for seg in script.segments)
    assert all(seg.est_duration_sec > 0 for seg in script.segments)
    assert script.total_duration_sec > 0

    # Intro references the topic; outro is a call to action.
    assert "space" in script.segments[0].text.lower()
    assert "follow" in script.segments[-1].text.lower()


def test_factory_returns_template_default():
    provider = get_script_provider("template")
    assert isinstance(provider, TemplateScriptProvider)


def test_n_cards_clamped_to_available():
    provider = TemplateScriptProvider()
    # Request more cards than the pack has; should not raise and should be bounded.
    script = provider.generate("space", n_cards=999)
    assert len(script.segments) >= 3
