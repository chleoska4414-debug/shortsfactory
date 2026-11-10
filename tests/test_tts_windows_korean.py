from __future__ import annotations

import os
import wave

import pytest

from shortsfactory.tts import get_tts_provider


@pytest.mark.skipif(os.name != "nt", reason="requires Windows SAPI")
def test_korean_voice_synthesizes_repeatably_with_distinct_delivery(tmp_path):
    voice = get_tts_provider("windows-ko")
    text = "새벽 네 시, 그는 다시 눈을 떴다."
    samples = []
    for index, role in enumerate(("male_lead", "male_lead", "female_lead", "supporting")):
        target = str(tmp_path / f"{index}.wav")
        try:
            path, duration = voice.synthesize_scene(text, target, role)
        except RuntimeError as exc:
            if "Install a Korean Windows desktop speech voice" in str(exc):
                pytest.skip("Korean SAPI voice is unavailable")
            raise
        assert path == target and duration > 0
        with wave.open(path, "rb") as wav:
            samples.append(wav.readframes(wav.getnframes()))
    assert samples[0] == samples[1]
    assert len({samples[0], samples[2], samples[3]}) == 3
