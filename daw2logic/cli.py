"""Command-line interface for daw2logic."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .convert import convert_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="daw2logic",
        description="Convert a DAWproject file to a Logic Pro .logicx project",
    )
    parser.add_argument("input", type=Path, help="input .dawproject file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="output .logicx bundle path",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="optional JSON file listing conversion warnings and stats",
    )
    args = parser.parse_args(argv)

    try:
        report = convert_file(args.input, args.output)
    except (FileNotFoundError, ValueError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {args.output}")
    print(
        f"  {report.instrument_tracks} instrument track(s), "
        f"{report.audio_tracks} audio track(s), "
        f"{report.midi_regions} MIDI region(s), "
        f"{report.audio_regions} audio region(s), "
        f"{report.tempo} BPM"
    )
    for warning in report.warnings:
        print(f"  warning: {warning}", file=sys.stderr)

    if args.report:
        payload = {
            "warnings": report.warnings,
            "skipped": report.skipped,
            "instrument_tracks": report.instrument_tracks,
            "audio_tracks": report.audio_tracks,
            "midi_regions": report.midi_regions,
            "audio_regions": report.audio_regions,
            "markers": report.markers,
            "tempo": report.tempo,
            "title": report.title,
        }
        args.report.write_text(json.dumps(payload, indent=2) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
