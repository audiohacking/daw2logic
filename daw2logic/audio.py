"""Prepare DAWproject audio for Logic regions."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

from .ir import AudioClip, Transport
from .time import beats_to_seconds

_STRETCH_TOLERANCE_SEC = 0.01


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


def _timeline_seconds(clip: AudioClip, transport: Transport, content_sec: float) -> float:
    if clip.duration > 0:
        return beats_to_seconds(clip.duration, transport)
    return content_sec


def needs_audio_processing(clip: AudioClip, transport: Transport, source: Path) -> bool:
    """True when warp/time-stretch requires baking a derived WAV (not pass-through)."""
    if not clip.algorithm or clip.algorithm == "none":
        return False
    content_start, content_end = content_range_seconds(clip)
    content_sec = max(0.0, content_end - content_start)
    timeline_sec = _timeline_seconds(clip, transport, content_sec)
    return abs(timeline_sec - content_sec) > _STRETCH_TOLERANCE_SEC


def pass_through_warnings(clip: AudioClip, source: Path, transport: Transport) -> list[str]:
    """Warnings when the embedded WAV is copied unchanged into the Logic bundle."""
    warnings: list[str] = []
    label = clip.name or source.name
    total_frames, rate, _, _ = _read_wav_info(source)
    full_sec = total_frames / rate if rate else 0.0
    content_start, content_end = content_range_seconds(clip)
    content_sec = max(0.0, content_end - content_start)

    if content_start > _STRETCH_TOLERANCE_SEC or content_sec < full_sec - _STRETCH_TOLERANCE_SEC:
        warnings.append(
            f"audio '{label}': source trim not applied — full file copied into Logic bundle"
        )
    if clip.warps:
        warnings.append(
            f"audio '{label}': warp markers not baked into audio — original file preserved"
        )
    if clip.algorithm and clip.algorithm != "none":
        timeline_sec = _timeline_seconds(clip, transport, content_sec)
        if abs(timeline_sec - content_sec) <= _STRETCH_TOLERANCE_SEC:
            warnings.append(
                f"audio '{label}': time-stretch ({clip.algorithm}) skipped — "
                f"timeline matches source length"
            )
    if clip.fade_in or clip.fade_out:
        warnings.append(
            f"audio '{label}': clip fades not imported "
            f"(fadeIn={clip.fade_in}, fadeOut={clip.fade_out})"
        )
    return warnings


def resolve_audio_clip(
    clip: AudioClip,
    source: Path,
    work_dir: Path,
    transport: Transport,
) -> tuple[Path, list[str]]:
    """Return a WAV path for Logic: original file unless warp/stretch requires processing."""
    if needs_audio_processing(clip, transport, source):
        return prepare_audio_clip(clip, source, work_dir, transport)
    return source, pass_through_warnings(clip, source, transport)


def _unpack_pcm(frames: bytes, nframes: int, channels: int, sampwidth: int) -> list[int]:
    if sampwidth == 2:
        fmt = f"<{nframes * channels}h"
        return list(struct.unpack(fmt, frames[: nframes * channels * sampwidth]))
    if sampwidth == 3:
        samples: list[int] = []
        frame_bytes = channels * 3
        for i in range(nframes):
            base = i * frame_bytes
            for ch in range(channels):
                offset = base + ch * 3
                samples.append(int.from_bytes(frames[offset : offset + 3], "little", signed=True))
        return samples
    raise ValueError(f"unsupported sample width: {sampwidth * 8}-bit")


def _pack_pcm(samples: list[int], channels: int, sampwidth: int) -> bytes:
    if sampwidth == 2:
        clamped = [max(-32768, min(32767, s)) for s in samples]
        return struct.pack(f"<{len(clamped)}h", *clamped)
    if sampwidth == 3:
        out = bytearray()
        for sample in samples:
            clamped = max(-8388608, min(8388607, sample))
            out.extend(int(clamped).to_bytes(3, "little", signed=True))
        return bytes(out)
    raise ValueError(f"unsupported sample width: {sampwidth * 8}-bit")


def _resample_linear(
    frames: bytes, channels: int, sampwidth: int, src_n: int, dst_n: int
) -> bytes:
    if src_n <= 0 or dst_n <= 0:
        return b""
    if src_n == dst_n:
        return frames

    samples = _unpack_pcm(frames, src_n, channels, sampwidth)
    out: list[int] = []
    for i in range(dst_n):
        pos = i * (src_n - 1) / max(dst_n - 1, 1)
        idx = int(pos)
        frac = pos - idx
        for ch in range(channels):
            a = samples[idx * channels + ch]
            b = samples[min(idx + 1, src_n - 1) * channels + ch]
            out.append(int(round(a + (b - a) * frac)))
    return _pack_pcm(out, channels, sampwidth)


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
    """Slice and resample audio when warp/time-stretch must be baked into a new WAV."""
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

    content_sec = (content_end - content_start) or (src_n / rate)
    timeline_sec = _timeline_seconds(clip, transport, content_sec)
    dst_n = max(1, int(round(timeline_sec * rate)))

    if abs(timeline_sec - content_sec) > _STRETCH_TOLERANCE_SEC:
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
