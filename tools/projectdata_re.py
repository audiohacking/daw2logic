#!/usr/bin/env python3
"""Diff ProjectData records between two .logicx bundles (EQ, color, FX RE)."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "third_party" / "LogicProFormatWriter"))

from logicx.projectdata import ProjectData, _u32, KART_CHAN, IVNE_IDX, IVNE_NAME  # noqa: E402


def _load(path: Path) -> ProjectData:
    pd = path / "Alternatives" / "000" / "ProjectData"
    if not pd.is_file():
        raise SystemExit(f"missing ProjectData: {pd}")
    return ProjectData.parse(pd.read_bytes())


def _ivne_name(raw: bytes) -> str:
    n = struct.unpack_from("<H", raw, IVNE_NAME)[0]
    off = IVNE_NAME + 2
    return raw[off : off + n * 2].decode("utf-16-le", errors="replace")


def _channel_names(pd: ProjectData) -> dict[int, str]:
    out: dict[int, str] = {}
    for r in pd.records:
        if r.tag == b"ivnE":
            ch = _u32(r.raw, IVNE_IDX)
            if ch >= 0x580000:
                out[ch] = _ivne_name(r.raw)
    return out


def _records_by_tag(pd: ProjectData, tag: bytes, *, idx_filter: int | None = None) -> list[tuple[int, bytes]]:
    rows: list[tuple[int, bytes]] = []
    for i, r in enumerate(pd.records):
        if r.tag != tag:
            continue
        if idx_filter is not None and len(r.raw) > 12 and _u32(r.raw, 8) != idx_filter:
            continue
        rows.append((i, bytes(r.raw)))
    return rows


def _diff_bytes(ra: bytes, rb: bytes, *, limit: int = 40) -> list[tuple[int, int, int]]:
    n = min(len(ra), len(rb))
    diffs = [(i, ra[i], rb[i]) for i in range(n) if ra[i] != rb[i]]
    if len(ra) != len(rb):
        diffs.append((n, len(ra), len(rb)))
    return diffs[:limit]


def _print_diff(label: str, ra: bytes, rb: bytes) -> None:
    diffs = _diff_bytes(ra, rb)
    if not diffs:
        print(f"  {label}: identical ({len(ra)} B)")
        return
    print(f"  {label}: {len(ra)} B -> {len(rb)} B, {len(_diff_bytes(ra, rb, limit=9999))} byte(s) differ")
    for off, a, b in diffs:
        if off >= min(len(ra), len(rb)):
            print(f"    @+{off:#x}: len {a} -> {b}")
        else:
            print(f"    @+{off:#04x}: {a:#04x} -> {b:#04x}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    ap.add_argument("--channel", type=lambda s: int(s, 0), help="ivnE channel idx filter")
    ap.add_argument("--tag", default="nCuA", help="record tag to diff (nCuA, karT, gRuA, qeSM, OCuA)")
    args = ap.parse_args()

    a = _load(args.before)
    b = _load(args.after)
    tag = args.tag.encode("ascii")
    names = _channel_names(b)

    ra = _records_by_tag(a, tag, idx_filter=args.channel)
    rb = _records_by_tag(b, tag, idx_filter=args.channel)
    print(f"=== {tag.decode()} diff ===")
    print(f"before: {len(ra)} record(s), after: {len(rb)} record(s)")
    if args.channel is not None:
        print(f"channel {args.channel:#x} ({names.get(args.channel, '?')})")

    for i, ((ia, ba), (ib, bb)) in enumerate(zip(ra, rb)):
        ch = _u32(bb, 8) if len(bb) > 12 else 0
        label = f"#{i} rec[{ib}] ch={ch:#x} {names.get(ch, '')}"
        _print_diff(label, ba, bb)
        if tag == tag and b"GAMETSPP" in bb and b"GAMETSPP" not in ba:
            print("    ** GAMETSPP appeared (likely plugin/EQ PST) **")

    extra_a = ra[len(rb) :]
    extra_b = rb[len(ra) :]
    if extra_a:
        print(f"  removed in after: {len(extra_a)} record(s)")
    if extra_b:
        print(f"  added in after: {len(extra_b)} record(s)")
        for ib, bb in extra_b:
            ch = _u32(bb, 8) if len(bb) > 12 else 0
            print(f"    new rec[{ib}] len={len(bb)} ch={ch:#x} {names.get(ch, '')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
