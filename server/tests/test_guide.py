import os
import re
import shutil
import subprocess

import pytest

from app.guide import Cue, Word, find_cues, snap_to_bars
from tests.conftest import wav_file


def words(*items):
    return [Word(t, s, e) for t, s, e in items]


def test_find_cues_handles_numbers_and_two_word_cues():
    ws = words(
        (" One,", 0.5, 0.8), (" two,", 1.0, 1.3), (" three,", 1.5, 1.8), (" four.", 2.0, 2.3),  # count-in: ignored
        (" Verse", 10.0, 10.4), (" one.", 10.5, 10.8),
        (" Pre", 30.0, 30.2), ("-chorus.", 30.2, 30.6),
        (" Chorus.", 45.0, 45.5), (" Chorus.", 46.0, 46.5),           # repeated: counted once
        (" Verse 2.", 70.0, 70.6),
        (" Bridge.", 100.0, 100.4),
        (" Pre chorus", 120.0, 120.6),
        (" Ending.", 150.0, 150.5),
    )
    assert [c.label for c in find_cues(ws)] == [
        "Verse 1", "Pre-Chorus", "Chorus", "Verse 2", "Bridge", "Pre-Chorus", "Ending",
    ]


def test_find_cues_ignores_lyrics_like_words():
    ws = words((" Way", 1, 1.2), (" maker", 1.2, 1.5), (" miracle", 1.6, 2.0), (" worker", 2.0, 2.4))
    assert find_cues(ws) == []


def test_snap_moves_cue_to_next_downbeat():
    # 120 BPM 4/4 -> 2 s bars, click starts at 0.5 s
    cues = [Cue("Verse 1", 7.0, 7.6), Cue("Chorus", 16.2, 16.8), Cue("Bridge", 20.3, 20.62)]
    assert snap_to_bars(cues, 120, 4, 0.5, 300) == [("Verse 1", 8.5), ("Chorus", 18.5), ("Bridge", 20.5)]


def test_snap_without_bpm_uses_spoken_time():
    assert snap_to_bars([Cue("Intro", 1.234, 1.5)], None, 4, 0, 60) == [("Intro", 1.23)]


def _click(path, bpm, start, beats, seconds, accent=True, first_beat=0, rate=44100):
    """A click track: a short 1 kHz blip on every beat, the downbeat louder when `accent`."""
    import wave

    import numpy as np

    audio = np.zeros(int(seconds * rate), dtype=np.float32)
    blip = np.sin(2 * np.pi * 1000 * np.arange(int(0.03 * rate)) / rate) * np.linspace(1, 0, int(0.03 * rate))
    beat, n = 60.0 / bpm, first_beat
    t = start
    while t + 0.05 < seconds:
        i = int(t * rate)
        audio[i : i + len(blip)] += blip * (0.9 if accent and n % beats == 0 else 0.5)
        t += beat
        n += 1
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((audio * 32767).astype("<i2").tobytes())
    return path


def test_click_grid_measures_tempo_and_finds_the_accented_downbeat(tmp_path):
    from app.guide import click_grid, tidy_bpm

    # 71.9 BPM; the click starts on beat 3 (a pickup), so the downbeat is two beats in.
    path = _click(tmp_path / "c.wav", 71.9, 0.37, 4, 240, first_beat=2)
    bpm, phase = click_grid(path, None, 4)
    assert abs(bpm - 71.9) < 0.02 and tidy_bpm(bpm) == 71.9
    beat = 60 / 71.9
    assert abs(phase - (0.37 + 2 * beat)) < 0.01
    # The typed BPM is a little off (72): the bars still follow the click to the end.
    bpm, phase = click_grid(path, 72, 4)
    bar = 4 * 60 / bpm
    last_downbeat = 0.37 + 2 * beat + 4 * beat * 70
    assert abs((last_downbeat - phase) / bar - round((last_downbeat - phase) / bar)) * bar < 0.02


def test_click_grid_without_accent_uses_first_click(tmp_path):
    from app.guide import click_grid

    path = _click(tmp_path / "c.wav", 120, 1.0, 4, 60, accent=False)
    bpm, phase = click_grid(path, None, 4)
    assert abs(bpm - 120) < 0.05 and abs(phase - 1.0) < 0.01


def test_click_grid_gives_up_on_silence(tmp_path, wav):
    from app.guide import click_grid

    path = tmp_path / "s.wav"
    path.write_bytes(wav(5))
    assert click_grid(path, 90, 4) == (90, 0.0)


def test_detection_uses_click_when_bpm_is_missing(web, wav, app, tmp_path):
    # Click at 60 BPM, 4/4, first beat at 0.5 s -> downbeats at 0.5, 4.5, 8.5 ...
    click = _click(tmp_path / "Click.wav", 60, 0.5, 4, 20).read_bytes()
    app.state.transcriber.words = words((" Verse", 3.0, 3.4), (" Chorus", 7.6, 8.1))
    song_id = _song_with_guide(web, wav, bpm="")
    web.post(
        f"/songs/{song_id}/tracks",
        data={"csrf": web.csrf},
        files=[wav_file("Click.wav", click), wav_file("Guide.wav", wav(20))],
    )
    page = web.get(f"/songs/{song_id}").text
    assert re.search(r"0:04.5</button>\s*<span>Verse", page)
    assert re.search(r"0:08.5</button>\s*<span>Chorus", page)
    from app.models import Song

    with app.state.session_factory() as db:
        song = db.get(Song, song_id)
        assert song.bpm == 60
        assert [round(s.start_seconds, 2) for s in sorted(song.sections, key=lambda s: s.start_seconds)] == [4.5, 8.5]


def _song_with_guide(web, wav, bpm="120"):
    r = web.post("/songs", data={"title": "Gratitude", "bpm": bpm, "key": "B", "csrf": web.csrf}, follow_redirects=False)
    song_id = int(re.search(r"/songs/(\d+)", r.headers["location"]).group(1))
    return song_id


def test_sections_added_automatically_after_upload(web, wav, app):
    app.state.transcriber.words = words((" Verse", 3.1, 3.5), (" one", 3.5, 3.8), (" Chorus", 9.2, 9.7))
    song_id = _song_with_guide(web, wav)
    web.post(
        f"/songs/{song_id}/tracks",
        data={"csrf": web.csrf},
        files=[wav_file("Click.wav", wav(20)), wav_file("Guide.wav", wav(20)), wav_file("Bass.wav", wav(20))],
    )
    page = web.get(f"/songs/{song_id}").text
    assert "Found 2 sections" in page
    assert re.search(r"0:04</button>\s*<span>Verse 1 <span class=\"auto-badge\"", page)
    assert "0:10</button>" in page and "Chorus" in page
    assert app.state.transcriber.calls == 1


def test_no_detection_without_guide_or_when_sections_typed(web, wav, app):
    song_id = _song_with_guide(web, wav)
    web.post(f"/songs/{song_id}/tracks", data={"csrf": web.csrf}, files=[wav_file("Bass.wav", wav(2))])
    assert app.state.transcriber.calls == 0
    web.post(f"/songs/{song_id}/sections", data={"name": "Intro", "start": "0", "csrf": web.csrf})
    web.post(f"/songs/{song_id}/tracks", data={"csrf": web.csrf}, files=[wav_file("Guide.wav", wav(2))])
    assert app.state.transcriber.calls == 0  # you typed sections in, so it leaves them alone


def test_detect_button_keeps_manual_sections_and_replaces_auto(web, wav, app):
    song_id = _song_with_guide(web, wav)
    app.state.transcriber.words = words((" Bridge", 5.0, 5.4))
    web.post(f"/songs/{song_id}/tracks", data={"csrf": web.csrf}, files=[wav_file("Guide.wav", wav(20))])
    web.post(f"/songs/{song_id}/sections", data={"name": "Tag", "start": "0:15", "csrf": web.csrf})
    app.state.transcriber.words = words((" Outro", 11.0, 11.4))
    web.post(f"/songs/{song_id}/sections/detect", data={"csrf": web.csrf})
    page = web.get(f"/songs/{song_id}").text
    assert "<span>Tag" in page and "<span>Outro" in page and "<span>Bridge" not in page


def test_failure_is_reported(web, wav, app):
    class Broken:
        def transcribe(self, path):
            raise RuntimeError("model download failed")

    app.state.transcriber = Broken()
    song_id = _song_with_guide(web, wav)
    web.post(f"/songs/{song_id}/tracks", data={"csrf": web.csrf}, files=[wav_file("Guide.wav", wav(2))])
    assert "model download failed" in web.get(f"/songs/{song_id}").text
    assert web.get(f"/songs/{song_id}/sections/status").json()["status"] == "failed"


def _spoken_guide(tmp_path, cues, voice, gap):
    """A guide track: espeak-ng says each cue, then `gap` seconds of near-silence (like a real guide)."""
    import wave

    import numpy as np

    from app.audio import read_mono

    parts, starts, pos = [], [], 0.0
    rng = np.random.default_rng(1)
    for cue in cues:
        out = tmp_path / "w.wav"
        subprocess.run(["espeak-ng", "-v", voice, "-s", "150", "-w", str(out), cue], check=True)
        samples, rate = read_mono(out)
        assert rate == 22050
        starts.append(pos)
        quiet = (rng.standard_normal(int(gap * rate) - len(samples)) * 0.0005).astype(np.float32)  # hiss
        parts += [samples, quiet]
        pos += gap
    audio = (np.clip(np.concatenate(parts), -1, 1) * 32767).astype("<i2")
    guide = tmp_path / "guide.wav"
    with wave.open(str(guide), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(audio.tobytes())
    return guide, starts


def test_speech_regions_find_each_spoken_cue(tmp_path):
    if not shutil.which("espeak-ng"):
        pytest.skip("espeak-ng not installed")
    from app.guide import load_for_whisper, speech_regions, stitch, unstitch

    cues = ["Intro", "Verse one", "Chorus", "Verse two", "Chorus", "Bridge", "Chorus", "Ending"]
    guide, starts = _spoken_guide(tmp_path, cues, "en-us", 24.0)
    audio = load_for_whisper(guide)
    regions = speech_regions(audio)
    assert len(regions) == len(cues)
    for (a, _b), s0 in zip(regions, starts):
        assert abs(a - s0) < 0.3
    clip, spans = stitch(audio, regions)
    assert len(clip) / 16000 < 30  # 3 minutes of guide -> a few seconds of speech
    for (offset, a, _b) in spans:
        assert abs(unstitch(offset + 0.25, spans) - (a + 0.25)) < 1e-6
    # A word Whisper places slightly early (in the gap before a piece) still maps to that piece
    from app.guide import Word, unstitch_word

    offset, a, b = spans[3]
    w = unstitch_word(Word("Verse", offset - 0.5, offset + 0.3), spans)
    assert w.start == a and a < w.end <= b


@pytest.mark.skipif(not os.environ.get("RUN_WHISPER"), reason="set RUN_WHISPER=1 to run the real speech model")
@pytest.mark.parametrize(
    "voice,cues,expected",
    [
        ("en-us", ["Intro", "Verse one", "Chorus", "Verse two", "Pre chorus", "Chorus", "Bridge", "Chorus", "Ending"],
         ["Intro", "Verse 1", "Chorus", "Verse 2", "Pre-Chorus", "Chorus", "Bridge", "Chorus", "Ending"]),
        ("es-419", ["Intro", "Verso uno", "Coro", "Verso dos", "Coro", "Puente", "Coro", "Final"],
         ["Intro", "Verso 1", "Coro", "Verso 2", "Coro", "Puente", "Coro", "Final"]),
    ],
    ids=["english", "spanish"],
)
def test_real_whisper_on_spoken_guide(tmp_path, voice, cues, expected):
    """End to end with the real model: espeak-ng says the cues 25 s apart (like a real
    guide, mostly silence), Whisper must hear every one."""
    if not shutil.which("espeak-ng"):
        pytest.skip("espeak-ng not installed")
    from app.config import _whisper_model
    from app.guide import WhisperTranscriber

    guide, starts = _spoken_guide(tmp_path, cues, voice, 25.0)
    t = WhisperTranscriber(_whisper_model(os.environ.get("SBS_WHISPER_MODEL", "")), tmp_path / "models")
    words = t.transcribe(guide)
    print([(w.text, round(w.start, 1)) for w in words])
    found = find_cues(words)
    labels = [c.label for c in found]
    if voice == "en-us":
        assert labels == expected
    else:
        # espeak's robotic Spanish "dos" is sometimes heard as "tres"; the cue itself must be right.
        strip = lambda xs: [re.sub(r" \d$", "", x) for x in xs]  # noqa: E731
        assert strip(labels) == strip(expected)
        assert all(x[-1].isdigit() for x in labels if x.startswith("Verso"))
    for c, s0 in zip(found, starts):
        assert abs(c.start - s0) < 1.5


def test_spanish_cues():
    words = [Word(w, i * 10.0, i * 10.0 + 0.5) for i, w in enumerate(
        ["Introducción", "Verso", "uno", "Pre", "coro", "Coro.", "Estrofa", "dos", "Puente", "Último", "coro", "Final"])]
    # numbers attach only when said right after the cue
    words[2] = Word("uno", 10.6, 11.0)
    words[7] = Word("dos", 60.6, 61.0)
    labels = [c.label for c in find_cues(words)]
    assert labels == ["Intro", "Verso 1", "Pre-Coro", "Coro", "Verso 2", "Puente", "Coro", "Final"]


def test_old_english_only_default_is_upgraded():
    from app.config import _whisper_model

    assert _whisper_model("") == "small"
    assert _whisper_model("base.en") == "small"
    assert _whisper_model("medium") == "medium"


def test_load_for_whisper_resamples_to_16k(tmp_path, wav):
    from app.guide import load_for_whisper

    p = tmp_path / "g.wav"
    p.write_bytes(wav(seconds=2, rate=48000, channels=2, bits=24))
    audio = load_for_whisper(p)
    assert audio.dtype.name == "float32" and abs(len(audio) - 32000) <= 1
