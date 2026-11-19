"""Key names and transposition."""

from __future__ import annotations

SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
_PITCH = {n: i for i, n in enumerate(SHARP_NAMES)} | {n: i for i, n in enumerate(FLAT_NAMES)}
# Keys conventionally written with flats (majors, then relative minors).
FLAT_KEYS = {"F", "Bb", "Eb", "Ab", "Db", "Gb", "Dm", "Gm", "Cm", "Fm", "Bbm", "Ebm"}


def transpose_key(key: str, semitones: int) -> str:
    """'E' +1 -> 'F', 'A' -2 -> 'G', 'Bbm' +2 -> 'Cm'. Empty key stays empty."""
    if not key:
        return ""
    minor = key.endswith("m")
    root = key[:-1] if minor else key
    if root not in _PITCH:
        return key
    pitch = (_PITCH[root] + semitones) % 12
    sharp = SHARP_NAMES[pitch] + ("m" if minor else "")
    flat = FLAT_NAMES[pitch] + ("m" if minor else "")
    if sharp == flat:
        return sharp
    return flat if flat in FLAT_KEYS else sharp
