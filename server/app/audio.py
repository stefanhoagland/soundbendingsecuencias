"""Minimal WAV header reader.

Python's `wave` module rejects 32-bit float and some extensible files, so we
walk the RIFF chunks ourselves. Only the header is read; audio data is never
loaded into memory.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from typing import BinaryIO

WAVE_FORMAT_PCM = 0x0001
WAVE_FORMAT_IEEE_FLOAT = 0x0003
WAVE_FORMAT_EXTENSIBLE = 0xFFFE


class InvalidWav(ValueError):
    pass


@dataclass(frozen=True)
class WavInfo:
    sample_rate: int
    channels: int
    bit_depth: int
    sample_format: str  # "pcm" or "float"
    data_bytes: int
    data_offset: int = 0

    @property
    def duration_seconds(self) -> float:
        frame = self.channels * (self.bit_depth // 8)
        if not frame or not self.sample_rate:
            return 0.0
        return self.data_bytes / frame / self.sample_rate


def read_wav_info(fh: BinaryIO) -> WavInfo:
    fh.seek(0, 2)
    file_size = fh.tell()
    fh.seek(0)
    header = fh.read(12)
    if len(header) < 12:
        raise InvalidWav("File is too short to be a WAV file")
    riff, _size, wave = struct.unpack("<4sI4s", header)
    if riff not in (b"RIFF", b"RF64") or wave != b"WAVE":
        raise InvalidWav("Not a WAV file (missing RIFF/WAVE header)")

    fmt: tuple[int, int, int, int] | None = None
    data_bytes: int | None = None
    data_offset = 0
    ds64_data_size: int | None = None

    while True:
        chunk_header = fh.read(8)
        if len(chunk_header) < 8:
            break
        chunk_id, chunk_size = struct.unpack("<4sI", chunk_header)
        start = fh.tell()
        if chunk_id == b"ds64":
            body = fh.read(min(chunk_size, 28))
            if len(body) >= 16:
                ds64_data_size = struct.unpack("<Q", body[8:16])[0]
        elif chunk_id == b"fmt ":
            body = fh.read(chunk_size)
            if len(body) < 16:
                raise InvalidWav("Corrupt fmt chunk")
            tag, channels, rate, _byte_rate, _align, bits = struct.unpack("<HHIIHH", body[:16])
            if tag == WAVE_FORMAT_EXTENSIBLE and len(body) >= 26:
                tag = struct.unpack("<H", body[24:26])[0]
            fmt = (tag, channels, rate, bits)
        elif chunk_id == b"data":
            data_offset = start
            if chunk_size == 0xFFFFFFFF and ds64_data_size is not None:
                data_bytes = ds64_data_size
            else:
                # Some writers leave the size wrong; never trust it past EOF.
                data_bytes = min(chunk_size, file_size - start)
            break
        fh.seek(start + chunk_size + (chunk_size & 1))

    if fmt is None:
        raise InvalidWav("WAV file has no fmt chunk")
    if data_bytes is None:
        raise InvalidWav("WAV file has no audio data")
    tag, channels, rate, bits = fmt
    if tag == WAVE_FORMAT_PCM:
        sample_format = "pcm"
    elif tag == WAVE_FORMAT_IEEE_FLOAT:
        sample_format = "float"
    else:
        raise InvalidWav(f"Unsupported WAV encoding (format tag {tag:#06x}); export as PCM or float")
    if channels < 1 or rate < 1 or bits not in (8, 16, 24, 32, 64):
        raise InvalidWav("WAV header has invalid channel, rate or bit-depth values")
    return WavInfo(rate, channels, bits, sample_format, data_bytes, data_offset)


_ROLE_PATTERNS = [
    ("click", re.compile(r"\b(click|clic|metronome|metr[oó]nomo|clk)\b", re.I)),
    ("guide", re.compile(r"\b(guides?|gu[ií]a|cues?|count|count ?in|conteo|vocal ?cues?)\b", re.I)),
]


def guess_role(filename: str) -> str:
    stem = re.sub(r"\.[^.]+$", "", filename).replace("_", " ").replace("-", " ")
    for role, pattern in _ROLE_PATTERNS:
        if pattern.search(stem):
            return role
    return "stem"


def track_name_from_filename(filename: str) -> str:
    name = re.sub(r"\.[^.]+$", "", filename)
    name = re.sub(r"[_]+", " ", name).strip()
    return name or "Track"


def read_mono(path, seconds: float | None = None):
    """Return (samples as float32 numpy array in -1..1, mixed to mono, sample rate)."""
    import numpy as np

    with open(path, "rb") as fh:
        info = read_wav_info(fh)
        frame = info.channels * info.bit_depth // 8
        nbytes = info.data_bytes
        if seconds is not None:
            nbytes = min(nbytes, int(seconds * info.sample_rate) * frame)
        nbytes -= nbytes % frame
        fh.seek(info.data_offset)
        raw = fh.read(nbytes)
    if info.sample_format == "float":
        data = np.frombuffer(raw, dtype="<f4" if info.bit_depth == 32 else "<f8").astype(np.float32)
    elif info.bit_depth == 8:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128
    elif info.bit_depth == 16:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
    elif info.bit_depth == 24:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v & 0x800000, v - 0x1000000, v)
        data = v.astype(np.float32) / 8388608
    else:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648
    data = data.reshape(-1, info.channels).mean(axis=1)
    return data, info.sample_rate
