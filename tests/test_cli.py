"""CLI output and conversion notes tests."""

from __future__ import annotations

from pathlib import Path

from daw2logic.cli import main
from daw2logic.convert import conversion_notes_path, format_conversion_notes


def test_conversion_notes_path():
    assert conversion_notes_path(Path("/tmp/song.logicx")) == Path("/tmp/song.txt")


def test_format_conversion_notes_dedupes_warnings():
    from daw2logic.convert import ConversionReport

    report = ConversionReport(
        warnings=["clip fades not imported"] * 3 + ["one-off warning"],
        audio_regions=2,
    )
    text = format_conversion_notes(
        report, source="in.dawproject", output="out.logicx"
    )
    assert "(3x) clip fades not imported" in text
    assert "one-off warning" in text
    assert "Warnings (4)" in text


def test_cli_is_quiet_and_writes_notes(capsys, bitwig_simple_dawproject, tmp_path):
    out = tmp_path / "out.logicx"
    notes = conversion_notes_path(out)
    rc = main([str(bitwig_simple_dawproject), "-o", str(out)])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert notes.is_file()
    body = notes.read_text()
    assert "daw2logic conversion notes" in body
    assert "Warnings" in body or "Summary" in body
