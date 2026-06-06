#!/usr/bin/env python3
"""
Compare OCuA channel strips between two Logic-made .logicx bundles.

Use this after changing ONLY volume/pan/mute on one track in Logic and re-saving,
to isolate fader field offsets for LogicProFormatWriter.

  python tools/ocua_mixer_re.py before.logicx after.logicx
  python tools/ocua_mixer_re.py before.logicx after.logicx --channel 0x580000
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "third_party" / "LogicProFormatWriter"))

from logicx.projectdata import OCUA_UUID, ProjectData, _ocua_for_channel  # noqa: E402


def _load(path: Path) -> ProjectData:
    pd = path / "Alternatives" / "000" / "ProjectData"
    if not pd.is_file():
        raise SystemExit(f"missing ProjectData: {pd}")
    return ProjectData.parse(pd.read_bytes())


def _active_strips(pd: ProjectData) -> dict[bytes, bytes]:
    out: dict[bytes, bytes] = {}
    for r in pd.records:
        if r.tag != b"OCuA" or len(r.raw) < OCUA_UUID + 16:
            continue
        u = r.raw[OCUA_UUID:OCUA_UUID + 16]
        if u != b"\x00" * 16:
            out[u] = r.raw
    return out


def _fmt_float(raw: bytes, off: int) -> str:
    if off + 4 > len(raw):
        return "?"
    v = struct.unpack_from("<f", raw, off)[0]
    return f"{v:.6g}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("before", type=Path, help="baseline .logicx bundle")
    ap.add_argument("after", type=Path, help="modified .logicx bundle")
    ap.add_argument("--channel", type=lambda s: int(s, 0), help="only diff this ivnE channel idx")
    args = ap.parse_args()

    a = _load(args.before)
    b = _load(args.after)
    sa = _active_strips(a)
    sb = _active_strips(b)
    common = set(sa) & set(sb)
    if not common:
        print("no linked OCuA strips in common (check both files are the same session)")
        return 1

    if args.channel is not None:
        oc_a = _ocua_for_channel(a, args.channel)
        oc_b = _ocua_for_channel(b, args.channel)
        if oc_a is None or oc_b is None:
            print(f"no strip for channel {args.channel:#x}")
            return 1
        pairs = [(oc_a.raw[OCUA_UUID:OCUA_UUID + 16], oc_a.raw, oc_b.raw)]
    else:
        pairs = [(u, sa[u], sb[u]) for u in sorted(common)]

    for uuid, ra, rb in pairs:
        if len(ra) != len(rb):
            print(f"UUID {uuid.hex()} length {len(ra)} -> {len(rb)}")
            continue
        diffs = [i for i in range(len(ra)) if ra[i] != rb[i]]
        if not diffs:
            continue
        print(f"\nOCuA UUID {uuid.hex()} — {len(diffs)} byte diffs")
        for i in diffs:
            line = f"  +0x{i:02x}: {ra[i]:02x} -> {rb[i]:02x}"
            if i % 4 == 0 and i + 4 <= len(ra):
                line += f"  (f: {_fmt_float(ra, i)} -> {_fmt_float(rb, i)})"
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
