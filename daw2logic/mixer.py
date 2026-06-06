# Logic Pro mixer channel-strip patching (OCuA fader/pan/mute offsets) is not yet
# reverse-engineered in LogicProFormatWriter. Track mixer and automation curves are
# exported to Media/daw2logic Import/ as JSON sidecars until native ProjectData
# writers exist.
#
# When offsets are known, set OCUA_*_OFF constants in mixer_logic.py and apply_mixer()
# will patch ProjectData on convert. Capture fixtures with tools/ocua_mixer_re.py
# (see scripts/re/README.md).

from daw2logic.mixer_logic import apply_mixer, patch_ocua_mixer  # noqa: F401

__all__ = ["apply_mixer", "patch_ocua_mixer"]
