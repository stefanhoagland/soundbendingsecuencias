"""Find section markers by listening to the guide track.

The guide track's spoken cues ("Verse one", "Chorus", "Bridge"...) are transcribed
locally with Whisper (faster-whisper, CPU, int8). Each cue is usually spoken in the
bar before the section, so it's snapped forward to the next downbeat using the
song's BPM and the click track's first beat.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("soundbending.guide")


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Cue:
    label: str
    start: float  # when the word was spoken
    end: float


# Spoken word -> section name. Order matters for multi-word cues (handled below).
_SECTION_WORDS = {
    "intro": "Intro",
    "verse": "Verse",
    "verses": "Verse",
    "prechorus": "Pre-Chorus",
    "chorus": "Chorus",
    "choruses": "Chorus",
    "postchorus": "Post-Chorus",
    "bridge": "Bridge",
    "tag": "Tag",
    "outro": "Outro",
    "ending": "Ending",
    "end": "Ending",
    "interlude": "Interlude",
    "instrumental": "Instrumental",
    "turnaround": "Turnaround",
    "vamp": "Vamp",
    "breakdown": "Breakdown",
    "refrain": "Refrain",
    "hook": "Hook",
    "build": "Build",
    "acapella": "A Cappella",
    "solo": "Solo",
}
# Spanish cues (labels stay in Spanish, the way the guide says them).
_SECTION_WORDS_ES = {
    "introduccion": "Intro",
    "verso": "Verso",
    "versos": "Verso",
    "estrofa": "Verso",
    "precoro": "Pre-Coro",
    "coro": "Coro",
    "coros": "Coro",
    "postcoro": "Post-Coro",
    "puente": "Puente",
    "interludio": "Interludio",
    "final": "Final",
    "finale": "Final",
    "despedida": "Final",
    "etiqueta": "Tag",
    "rap": "Rap",
}
_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "first": 1, "second": 2, "third": 3, "fourth": 4,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
    "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "primero": 1, "primer": 1, "primera": 1, "segundo": 2, "segunda": 2, "tercero": 3, "tercer": 3, "tercera": 3,
    "cuarto": 4, "cuarta": 4,
}
_NUMBERED = {"Verse", "Chorus", "Pre-Chorus", "Bridge", "Interlude", "Tag", "Verso", "Coro", "Pre-Coro", "Puente", "Interludio"}

# Prompt nudges Whisper towards spelling the cues the way we look for them.
INITIAL_PROMPT = "Intro. Verse 1. Pre-Chorus. Chorus. Verse 2. Bridge. Interlude. Instrumental. Turnaround. Tag. Vamp. Outro. Ending."
PROMPTS = {
    "en": INITIAL_PROMPT,
    "es": "Intro. Verso 1. Pre coro. Coro. Verso 2. Puente. Interludio. Instrumental. Coro. Final.",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return re.sub(r"[^a-z0-9]", "", text.encode("ascii", "ignore").decode())


def find_cues(words: list[Word]) -> list[Cue]:
    """Pick section cues out of a word-level transcript."""
    toks = []
    for w in words:
        # Whisper sometimes returns "Pre-Chorus" or "Verse 2" as one token.
        for part in re.split(r"[\s]+", w.text.strip()):
            if part:
                toks.append(Word(part, w.start, w.end))
    cues: list[Cue] = []
    i = 0
    while i < len(toks):
        n = _norm(toks[i].text)
        start, end = toks[i].start, toks[i].end
        label = None
        nxt = _norm(toks[i + 1].text) if i + 1 < len(toks) else ""
        # "pre chorus" / "post chorus" / "pre coro" / "a cappella" as two words
        if n in ("pre", "post") and nxt in ("chorus", "choruses", "coro", "coros"):
            es = nxt.startswith("coro")
            label = ("Pre-" if n == "pre" else "Post-") + ("Coro" if es else "Chorus")
            end, i = toks[i + 1].end, i + 1
        elif n == "a" and nxt in ("cappella", "capella"):
            label, end, i = "A Cappella", toks[i + 1].end, i + 1
        elif n in ("verso1", "verso2", "verso3", "verso4", "coro1", "coro2", "coro3", "puente1", "puente2"):
            base = "Verso" if n.startswith("verso") else "Coro" if n.startswith("coro") else "Puente"
            label = f"{base} {n[-1]}"
        elif n in _SECTION_WORDS_ES:
            label = _SECTION_WORDS_ES[n]
        elif n in ("verse1", "verse2", "verse3", "verse4", "chorus1", "chorus2", "chorus3", "bridge1", "bridge2"):
            base = "Verse" if n.startswith("verse") else "Chorus" if n.startswith("chorus") else "Bridge"
            label = f"{base} {n[-1]}"
        elif n in _SECTION_WORDS:
            label = _SECTION_WORDS[n]
        if label:
            # Attach a number said right after ("Verse ... two").
            if label in _NUMBERED and not label[-1].isdigit() and i + 1 < len(toks):
                nxt = toks[i + 1]
                num = _NUMBERS.get(_norm(nxt.text))
                if num and nxt.start - end < 1.0:
                    label, end, i = f"{label} {num}", nxt.end, i + 1
            cues.append(Cue(label, start, end))
        i += 1
    # The same cue repeated within a few seconds ("Chorus... chorus") counts once.
    out: list[Cue] = []
    for c in cues:
        if out and out[-1].label == c.label and c.start - out[-1].end < 4.0:
            continue
        out.append(c)
    return out


def snap_to_bars(cues: list[Cue], bpm: float | None, beats_per_bar: int, phase: float, duration: float) -> list[tuple[str, float]]:
    """Move each cue to the first downbeat after it was spoken."""
    out: list[tuple[str, float]] = []
    if not bpm:
        return [(c.label, round(c.start, 2)) for c in cues]
    bar = beats_per_bar * 60.0 / bpm
    for c in cues:
        t = c.end - 0.12  # a word that ends right on the downbeat belongs to that downbeat
        k = math.ceil((t - phase) / bar)
        start = phase + k * bar
        if duration and start >= duration:
            continue
        out.append((c.label, round(max(0.0, start), 3)))
    # Two cues landing on the same bar: keep the later one (it's the correction).
    dedup: dict[float, str] = {}
    for label, t in out:
        dedup[t] = label
    return sorted(((label, t) for t, label in dedup.items()), key=lambda x: x[1])


def click_phase(path: Path, bpm: float | None, beats_per_bar: int) -> float:
    """Time of the click's first beat, folded into one bar. 0 if it can't be found."""
    if not bpm:
        return 0.0
    try:
        import numpy as np

        from .audio import read_mono

        samples, rate = read_mono(path, seconds=30)
        if not len(samples):
            return 0.0
        env = np.abs(samples)
        peak = float(env.max())
        if peak < 1e-3:
            return 0.0
        first = int(np.argmax(env > peak * 0.3))
        bar = beats_per_bar * 60.0 / bpm
        return (first / rate) % bar
    except Exception:  # noqa: BLE001 - a bad click file just means no phase
        log.exception("Couldn't read click track for bar phase")
        return 0.0


def load_for_whisper(path: Path):
    """Read the WAV ourselves (any bit depth, float, RF64) as 16 kHz mono float32,
    rather than relying on the PyAV decoder inside faster-whisper."""
    import numpy as np

    from .audio import read_mono

    samples, rate = read_mono(path)
    if rate != 16000 and len(samples):
        n = int(round(len(samples) * 16000 / rate))
        samples = np.interp(np.linspace(0, len(samples) - 1, n), np.arange(len(samples)), samples)
    return np.ascontiguousarray(samples, dtype=np.float32)


class WhisperTranscriber:
    """Loads the model on first use and keeps it in memory."""

    def __init__(self, model_name: str, models_dir: Path):
        self.model_name = model_name
        self.models_dir = models_dir
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            log.info("Loading Whisper model %s (first run downloads it to %s)", self.model_name, self.models_dir)
            self._model = WhisperModel(
                self.model_name, device="cpu", compute_type="int8", download_root=str(self.models_dir)
            )
        return self._model

    def transcribe(self, path: Path) -> list[Word]:
        audio = load_for_whisper(path)
        regions = speech_regions(audio)
        if regions:
            clip, spans = stitch(audio, regions)
        else:
            clip, spans = audio, [(0.0, 0.0, len(audio) / SR)]
        with self._lock:
            model = self._load()
            lang = self._language(model, clip)
            segments, _info = model.transcribe(
                clip,
                language=lang,
                word_timestamps=True,
                initial_prompt=PROMPTS.get(lang, INITIAL_PROMPT),
                condition_on_previous_text=False,
                vad_filter=False,  # silence is already cut out
                beam_size=5,
            )
            words = [Word(w.word, w.start, w.end) for seg in segments for w in (seg.words or [])]
        return [Word(w.text, unstitch(w.start, spans), unstitch(w.end, spans)) for w in words]

    def _language(self, model, clip) -> str:
        """English-only models are always "en"; otherwise ask the model (guides are English or Spanish)."""
        if self.model_name.endswith(".en"):
            return "en"
        try:
            _lang, _p, probs = model.detect_language(clip[: SR * 30])
            scores = dict(probs)
            return "es" if scores.get("es", 0) > scores.get("en", 0) else "en"
        except Exception:  # noqa: BLE001 - older faster-whisper: let transcribe detect it
            log.exception("Language detection failed; assuming English")
            return "en"


# ---- cutting the silence out -----------------------------------------------------
# Guide tracks are mostly silence with a word every 20-40 seconds. Whisper reads audio
# in 30-second windows and tends to drop lone words in long silent stretches, so we find
# where someone is speaking, butt those bits together with short gaps, and map the
# word times back afterwards.

SR = 16000
FRAME = 320  # 20 ms
GAP = 0.6  # silence put between stitched pieces, seconds


def speech_regions(audio, min_len: float = 0.12, join: float = 0.45, pad: float = 0.2) -> list[tuple[float, float]]:
    """(start, end) seconds where the guide track has a voice, from frame loudness."""
    import numpy as np

    n = len(audio) // FRAME
    if n == 0:
        return []
    frames = np.asarray(audio[: n * FRAME], dtype=np.float32).reshape(n, FRAME)
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    peak = float(np.percentile(db, 99.5))
    if peak < -60:
        return []
    loud = db > max(peak - 30.0, -55.0)
    regions: list[list[float]] = []
    t = FRAME / SR
    for k in np.flatnonzero(loud):
        a, b = k * t, (k + 1) * t
        if regions and a - regions[-1][1] <= join:
            regions[-1][1] = b
        else:
            regions.append([a, b])
    total = len(audio) / SR
    out = [(max(0.0, a - pad), min(total, b + pad)) for a, b in regions if b - a >= min_len]
    # Padding can make neighbours overlap; merge them.
    merged: list[tuple[float, float]] = []
    for a, b in out:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


def stitch(audio, regions):
    """One short clip of just the speech. Returns (clip, spans) where each span is
    (offset in clip, start in original, end in original)."""
    import numpy as np

    gap = np.zeros(int(GAP * SR), dtype=np.float32)
    parts, spans, pos = [], [], 0.0
    for a, b in regions:
        piece = audio[int(a * SR): int(b * SR)]
        spans.append((pos, a, b))
        parts += [piece, gap]
        pos += len(piece) / SR + GAP
    return np.ascontiguousarray(np.concatenate(parts), dtype=np.float32), spans


def unstitch(t: float, spans) -> float:
    """Clip time -> original track time."""
    best = spans[0]
    for span in spans:
        if span[0] <= t:
            best = span
        else:
            break
    offset, a, b = best
    return min(a + (t - offset), b)
