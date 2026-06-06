"""Apply DAWproject transport data to a Logic .logicx bundle."""

from __future__ import annotations

import plistlib
from pathlib import Path

from logicx.projectdata import ProjectData

from .ir import Marker, Transport
from .time import PPQ, beats_to_tick, build_time_map


def apply_transport(logicx_dir: Path, transport: Transport, markers: tuple[Marker, ...]) -> list[str]:
    """Patch ProjectData and MetaData with tempo, meter, and markers."""
    warnings: list[str] = []
    alt = logicx_dir / "Alternatives" / "000"
    pd_path = alt / "ProjectData"
    pd = ProjectData.parse(pd_path.read_bytes())

    time_map = build_time_map(transport)
    tempo_pts = transport.tempo_map or ()
    meter_pts = transport.meter_map or ()

    if len(tempo_pts) > 1:
        pd.set_tempo_map([(beats_to_tick(p.time, time_map), p.bpm) for p in tempo_pts], ppq=PPQ)
        bpm = tempo_pts[0].bpm
    else:
        bpm = transport.tempo
        pd.set_tempo(bpm)

    init_num, init_den = transport.numerator, transport.denominator
    if len(meter_pts) > 1 or (
        meter_pts
        and (meter_pts[0].numerator, meter_pts[0].denominator) != (init_num, init_den)
    ):
        points = meter_pts or ()
        pd.set_meter_map(
            [(beats_to_tick(p.time, time_map), p.numerator, p.denominator) for p in points],
            ppq=PPQ,
        )
        init_num, init_den = points[0].numerator, points[0].denominator

    if markers:
        try:
            pd.set_markers(
                [(beats_to_tick(m.time, time_map), m.name) for m in markers],
                ppq=PPQ,
            )
        except ValueError as exc:
            warnings.append(f"markers not written: {exc}")

    pd_path.write_bytes(pd.serialize())

    md_path = alt / "MetaData.plist"
    md = plistlib.loads(md_path.read_bytes())
    md["BeatsPerMinute"] = float(bpm)
    md["SongSignatureNumerator"] = int(init_num)
    md["SongSignatureDenominator"] = int(init_den)
    md_path.write_bytes(plistlib.dumps(md, fmt=plistlib.FMT_BINARY))
    return warnings
