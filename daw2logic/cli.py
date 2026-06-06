"""Command-line interface for daw2logic."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .convert import convert_file, write_conversion_notes


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
        help="optional JSON report path (default: notes written beside output as .txt)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="overwrite an existing output .logicx bundle",
    )
    args = parser.parse_args(argv)

    try:
        report = convert_file(args.input, args.output, force=args.force)
    except (FileNotFoundError, ValueError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    write_conversion_notes(report, source=args.input, output=args.output)

    if args.report:
        payload = {
            "warnings": report.warnings,
            "skipped": report.skipped,
            "instrument_tracks": report.instrument_tracks,
            "audio_tracks": report.audio_tracks,
            "midi_regions": report.midi_regions,
            "audio_regions": report.audio_regions,
            "markers": report.markers,
            "plugins_copied": report.plugins_copied,
            "tempo": report.tempo,
            "title": report.title,
            "mixer_patched_tracks": sorted(report.mixer_patched_tracks),
            "color_patched_tracks": sorted(report.color_patched_tracks),
        }
        args.report.write_text(json.dumps(payload, indent=2) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
