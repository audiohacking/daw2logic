"""Export plugin, mixer, and automation sidecars into the Logic bundle."""

from __future__ import annotations

import json
import plistlib
import shutil
from pathlib import Path

from .aupreset import component_summary, read_aupreset
from .ir import Project, Track

IMPORT_ROOT = Path("Media") / "daw2logic Import"


def _safe_dir_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:64] or "track"


def _track_mixer(track: Track) -> dict | None:
    if track.volume is None and track.pan is None and track.mute is None and not track.solo:
        return None
    return {
        "volume_linear": track.volume,
        "pan_normalized": track.pan,
        "mute": track.mute,
        "solo": track.solo,
    }


def export_sidecars(logicx_dir: Path, project: Project, report) -> None:
    """Write import manifests and copied AU presets under Media/daw2logic Import/."""
    root = logicx_dir / IMPORT_ROOT
    plugins_dir = root / "plugins"
    automation_dir = root / "automation"
    root.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "source": str(project.source.name),
        "title": project.metadata.title,
        "tracks": [],
        "notes": [
            "AU presets are copied for manual loading in Logic Pro (Channel Strip settings).",
            "Mixer JSON is a fallback reference; audio track volume is written to ProjectData when supported.",
        ],
    }

    plugins_copied = 0
    for track in project.tracks:
        entry: dict = {"name": track.name, "content_type": track.content_type}
        mixer = _track_mixer(track)
        if mixer:
            entry["mixer"] = mixer
            if _mixer_is_non_default(track) and track.name not in report.mixer_patched_tracks:
                report.warnings.append(
                    f"track '{track.name}': mixer values exported to sidecar only "
                    "(Logic channel strips not patched)"
                )

        track_plugins: list[dict] = []
        for plugin in track.plugins:
            pinfo = {
                "kind": plugin.kind,
                "name": plugin.name,
                "device_id": plugin.device_id,
                "vendor": plugin.vendor,
                "role": plugin.role,
                "enabled": plugin.enabled,
                "state_path": plugin.state_path,
            }
            if plugin.kind == "au" and plugin.resolved_path and plugin.resolved_path.is_file():
                dest_dir = plugins_dir / _safe_dir_name(track.name)
                dest_dir.mkdir(parents=True, exist_ok=True)
                ext = plugin.resolved_path.suffix or ".aupreset"
                dest = dest_dir / f"{_safe_dir_name(plugin.name or 'preset')}{ext}"
                shutil.copy2(plugin.resolved_path, dest)
                rel = dest.relative_to(logicx_dir).as_posix()
                pinfo["bundled_path"] = rel
                try:
                    au_info = read_aupreset(dest)
                    pinfo["au_component"] = component_summary(au_info)
                    pinfo["preset_name"] = au_info.name
                    pinfo["payload_bytes"] = au_info.payload_size
                except (ValueError, plistlib.InvalidFileException, OSError) as exc:
                    report.warnings.append(
                        f"track '{track.name}': could not parse AU preset: {exc}"
                    )
                plugins_copied += 1
                report.skipped.append(
                    f"track '{track.name}': AU preset copied to {rel} — load manually in Logic"
                )
            elif plugin.kind != "au":
                report.skipped.append(
                    f"track '{track.name}': {plugin.kind.upper()} plugin "
                    f"'{plugin.name or plugin.device_id}' (no Logic slot)"
                )
            track_plugins.append(pinfo)
        if track_plugins:
            entry["plugins"] = track_plugins
        if track.automation:
            entry["automation"] = track.automation
            automation_dir.mkdir(parents=True, exist_ok=True)
            auto_path = automation_dir / f"{_safe_dir_name(track.name)}.json"
            auto_path.write_text(json.dumps(track.automation, indent=2) + "\n")
            entry["automation_sidecar"] = auto_path.relative_to(logicx_dir).as_posix()
            report.warnings.append(
                f"track '{track.name}': automation exported to sidecar only"
            )
        if track.color:
            entry["color"] = track.color
        manifest["tracks"].append(entry)

    manifest["plugins_copied"] = plugins_copied
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (root / "README.txt").write_text(
        "daw2logic import sidecar\n"
        "=======================\n"
        "AU presets: drag .aupreset files from plugins/ onto instrument channel strips in Logic.\n"
        "mixer/automation JSON: reference for manual recall; not applied to ProjectData yet.\n"
        "See manifest.json for per-track details.\n"
    )
    report.plugins_copied = plugins_copied


def _mixer_is_non_default(track: Track) -> bool:
    vol_ok = track.volume is None or abs(track.volume - 1.0) < 1e-6
    pan_ok = track.pan is None or abs(track.pan - 0.5) < 1e-6
    mute_ok = track.mute in (None, False)
    return not (vol_ok and pan_ok and mute_ok)
