"""Tests for Logic channel mapping and mixer patching hooks."""

from __future__ import annotations

from pathlib import Path

import pytest

from daw2logic.convert import convert_file
from daw2logic.logicx_channels import audio_channels, instrument_channels
from daw2logic.mixer_logic import OCUA_VOLUME_LINEAR_OFF, apply_mixer, patch_ocua_mixer
from logicx.projectdata import ProjectData


def test_instrument_and_audio_channel_maps(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    pd = ProjectData.parse((logicx_output / "Alternatives" / "000" / "ProjectData").read_bytes())
    inst = instrument_channels(pd)
    aud = audio_channels(pd)
    assert 1 in inst and 1 in aud
    assert inst[1] != aud[1]


def test_patch_ocua_mixer_inactive_strip():
    inactive = b"\x00" * 205
    assert patch_ocua_mixer(inactive, volume_linear=0.5) is None


def test_apply_mixer_noop_without_offsets(bitwig_simple_dawproject, logicx_output):
    report = convert_file(bitwig_simple_dawproject, logicx_output)
    before = (logicx_output / "Alternatives" / "000" / "ProjectData").read_bytes()
    assert OCUA_VOLUME_LINEAR_OFF is None
    from daw2logic.parser import cleanup, load

    project = load(bitwig_simple_dawproject)
    try:
        apply_mixer(logicx_output, project, report)
    finally:
        cleanup(project)
    after = (logicx_output / "Alternatives" / "000" / "ProjectData").read_bytes()
    assert before == after
