"""Tests for plugin and sidecar export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from daw2logic.aupreset import read_aupreset
from daw2logic.convert import convert_file
from daw2logic.parser import cleanup, load


def test_read_logicfiles_aupreset():
    preset = Path("third_party/LogicFiles/Tests/Resources/PP.aupreset")
    if not preset.is_file():
        pytest.skip("LogicFiles submodule not initialized")
    info = read_aupreset(preset)
    assert info.payload_size > 0


def test_convert_au_sidecar(bitwig_au_dawproject, logicx_output):
    report = convert_file(bitwig_au_dawproject, logicx_output)
    assert report.plugins_copied == 1
    manifest = logicx_output / "Media/daw2logic Import/manifest.json"
    assert manifest.is_file()
    data = json.loads(manifest.read_text())
    assert data["plugins_copied"] == 1
    track = data["tracks"][0]
    assert track["plugins"][0]["kind"] == "au"
    assert "bundled_path" in track["plugins"][0]
    preset = logicx_output / track["plugins"][0]["bundled_path"]
    assert preset.is_file()
    assert track.get("automation_sidecar")


def test_parse_au_automation(bitwig_au_dawproject):
    project = load(bitwig_au_dawproject)
    try:
        track = project.tracks[0]
        assert len(track.automation) == 1
        assert track.automation[0]["target"] == "Volume"
        assert len(track.automation[0]["points"]) == 2
    finally:
        cleanup(project)
