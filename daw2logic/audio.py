"""Prepare DAWproject audio for Logic regions."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

from .ir import AudioClip, Transport
from .time import beats_to_seconds


def _read_wav_info(path: Path) -> tuple[int, int, int, int]:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes(), wf.getframerate(), wf.getnchannels(), wf.getsampwidth()


def _interp_warp(timeline_t: float, warps: tuple) -> float:
    pts = sorted(warps, key=lambda w: w.time)
    if timeline_t <= pts[0].time:
        return pts[0].content_time
    for w0, w1 in zip(pts, pts[1:]):
        if w0.time <= timeline_t <= w1.time:
            if w1.time == w0.time:
                return w0.content_time
            frac = (timeline_t - w0.time) / (w1.time - w0.time)
            return w0.content_time + frac * (w1.content_time - w0.content_time)
    return pts[-1].content_time


def content_range_seconds(clip: AudioClip) -> tuple[float, float]:
    """Map clip playStart..playStart+duration through warp markers to source seconds."""
    if clip.warps:
        t0 = clip.play_start
        t1 = clip.play_start + clip.duration
        return _interp_warp(t0, clip.warps), _interp_warp(t1, clip.warps)
    return clip.play_start, clip.play_start + clip.duration


def _resample_linear(
    frames: bytes, channels: int, sampwidth: int, src_n: int, dst_n: int
) -> bytes:
    if src_n <= 0 or dst_n <= 0:
        return b""
    if src_n == dst_n:
        return frames
    if sampwidth != 2:
        raise ValueError(f"unsupported sample width: {sampwidth * 8}-bit")

    fmt = f"<{src_n * channels}h"
    samples = list(struct.unpack(fmt, frames[: src_n * channels * sampwidth]))
    out: list[int] = []
    for i in range(dst_n):
        pos = i * (src_n - 1) / max(dst_n - 1, 1)
        idx = int(pos)
        frac = pos - idx
        for ch in range(channels):
            a = samples[idx * channels + ch]
            b = samples[min(idx + 1, src_n - 1) * channels + ch]
            out.append(int(round(a + (b - a) * frac)))
    out_fmt = f"<{dst_n * channels}h"
    return struct.pack(out_fmt, *out)


def _write_wav(path: Path, frames: bytes, rate: int, channels: int, sampwidth: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(rate)
        wf.writeframes(frames)


def prepare_audio_clip(
    clip: AudioClip,
    source: Path,
    work_dir: Path,
    transport: Transport,
) -> tuple[Path, list[str]]:
    """Slice and optionally resample audio; return a WAV path and warnings."""
    warnings: list[str] = []
    total_frames, rate, channels, sampwidth = _read_wav_info(source)

    content_start, content_end = content_range_seconds(clip)
    start_frame = max(0, int(round(content_start * rate)))
    end_frame = min(total_frames, int(round(content_end * rate)))
    if end_frame <= start_frame:
        end_frame = min(total_frames, start_frame + 1)

    with wave.open(str(source), "rb") as wf:
        wf.setpos(start_frame)
        raw = wf.readframes(end_frame - start_frame)
    src_n = end_frame - start_frame

    timeline_sec = beats_to_seconds(clip.duration, transport) if clip.duration > 0 else (
        (content_end - content_start)
    )
    content_sec = (content_end - content_start) or (src_n / rate)
    dst_n = max(1, int(round(timeline_sec * rate)))

    if clip.algorithm and clip.algorithm != "none" and abs(timeline_sec - content_sec) > 0.01:
        warnings.append(
            f"audio '{clip.name or source.name}': time-stretch ({clip.algorithm}) "
            f"approximated by resampling {content_sec:.3f}s -> {timeline_sec:.3f}s"
        )
        raw = _resample_linear(raw, channels, sampwidth, src_n, dst_n)
    elif dst_n < src_n:
        raw = _resample_linear(raw, channels, sampwidth, src_n, dst_n)
    elif dst_n > src_n:
        warnings.append(
            f"audio '{clip.name or source.name}': region shorter than source slice "
            f"({dst_n} vs {src_n} frames); truncating"
        )
        raw = raw[: dst_n * channels * sampwidth]

    if clip.fade_in or clip.fade_out:
        warnings.append(
            f"audio '{clip.name or source.name}': clip fades not imported "
            f"(fadeIn={clip.fade_in}, fadeOut={clip.fade_out})"
        )

    stem = Path(clip.path).stem
    out = work_dir / (
        f"{stem}_{int(clip.start * 1000)}_{int(clip.play_start * 1000)}"
        f"_{int(content_start * 1000)}.wav"
    )
    _write_wav(out, raw, rate, channels, sampwidth)
    return out, warnings
