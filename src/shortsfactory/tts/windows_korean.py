"""Offline Korean speech through an installed Windows SAPI voice."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import wave
from xml.sax.saxutils import escape

from .base import TTSProvider

# Rate and pitch adjustments for the installed Korean voice.
_DELIVERY = {"male_lead": (-2, -5), "female_lead": (0, 1), "supporting": (1, 0)}
_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$data = [Console]::In.ReadLine()
$payload = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($data)) | ConvertFrom-Json
$voice = New-Object -ComObject SAPI.SpVoice
$voices = $voice.GetVoices('Language=412')
if ($voices.Count -eq 0) { throw 'Install a Korean Windows desktop speech voice (e.g. Microsoft Heami).' }
$voice.Voice = $voices.Item(0)
$voice.Rate = $payload.rate
$stream = New-Object -ComObject SAPI.SpFileStream
$stream.Open($payload.path, 3, $false)
try {
    $voice.AudioOutputStream = $stream
    [void]$voice.Speak($payload.xml, 8)
} finally {
    $stream.Close()
}
"""


class WindowsKoreanTTS(TTSProvider):
    def synthesize(self, text: str, out_path: str):
        return self.synthesize_scene(text, out_path, None)

    def synthesize_scene(self, text: str, out_path: str, speaker_role: str | None):
        if os.name != "nt":
            raise RuntimeError("The windows-ko provider requires Windows and a Korean SAPI voice.")
        rate, pitch = _DELIVERY.get(speaker_role, (-1, -2))
        payload = json.dumps({
            "rate": rate,
            "path": os.path.abspath(out_path),
            "xml": f'<pitch middle="{pitch}">{escape(text)}</pitch>',
        })
        data = base64.b64encode(payload.encode("utf-8")) + b"\n"
        command = base64.b64encode(_SCRIPT.encode("utf-16-le")).decode("ascii")
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
            input=data, capture_output=True, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Korean SAPI synthesis failed: {detail}")
        with wave.open(out_path, "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
        return out_path, duration
