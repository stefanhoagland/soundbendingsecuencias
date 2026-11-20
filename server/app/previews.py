"""Small AAC copies of each stem for the browser player.

Full WAV stems are huge (a 12-stem song is often 500 MB+), and the web player
has to download every stem before it can start. So the server keeps a
compressed copy next to each WAV (<uuid>.m4a, about a tenth of the size) and the
player loads those. Every stem is encoded the same way, so any encoder delay is
identical on all of them and they stay in sync with each other. The WAVs are
never touched: downloads and the Mac app still get the originals.
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import select

from .models import Song, Track
from .storage import preview_path, track_path

log = logging.getLogger("soundbending.previews")

MEDIA_TYPE = "audio/mp4"


def song_ready(library_dir: Path, song: Song) -> bool:
    """True when every stem of the song has its preview, so the player can use them all.
    (Mixing previews with WAVs could put the two a few milliseconds apart.)"""
    return bool(song.tracks) and all(
        preview_path(library_dir, song.id, t.stored_filename).exists() for t in song.tracks
    )


def encode(src: Path, dst: Path) -> None:
    """WAV -> AAC in an MP4 container. Mono stays mono (128k), everything else is stereo (192k)."""
    import av  # bundled with faster-whisper; imported lazily so the web app starts fast

    partial = dst.with_name(dst.name + ".part")
    try:
        with av.open(str(src)) as inp, av.open(str(partial), "w", format="mp4") as out:
            ain = inp.streams.audio[0]
            mono = (ain.codec_context.channels or 2) == 1
            layout = "mono" if mono else "stereo"
            rate = ain.codec_context.sample_rate or 48000
            aout = out.add_stream("aac", rate=rate)
            aout.layout = layout
            aout.bit_rate = 128_000 if mono else 192_000
            resampler = av.AudioResampler(format="fltp", layout=layout, rate=rate)
            for frame in inp.decode(ain):
                for f in resampler.resample(frame):
                    for packet in aout.encode(f):
                        out.mux(packet)
            for f in resampler.resample(None):
                for packet in aout.encode(f):
                    out.mux(packet)
            for packet in aout.encode(None):
                out.mux(packet)
        os.replace(partial, dst)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


class PreviewMaker:
    """One background worker that makes any missing previews. `kick()` is cheap and
    can be called after every upload; repeated kicks while it runs fold into one more pass."""

    def __init__(self, library_dir: Path, session_factory):
        self.library_dir = library_dir
        self.session_factory = session_factory
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="previews")
        self._lock = threading.Lock()
        self._pending = False
        self._failed: set[Path] = set()

    def kick(self) -> None:
        with self._lock:
            if self._pending:
                return
            self._pending = True
        self._pool.submit(self._run)

    def _run(self) -> None:
        with self._lock:
            self._pending = False
        try:
            self.make_missing()
        except Exception:
            log.exception("Making playback previews failed")

    def make_missing(self) -> int:
        with self.session_factory() as db:
            todo = [(t.song_id, t.stored_filename) for t in db.scalars(select(Track).order_by(Track.song_id, Track.position))]
        made = 0
        for song_id, stored in todo:
            src = track_path(self.library_dir, song_id, stored)
            dst = preview_path(self.library_dir, song_id, stored)
            if dst.exists() or not src.exists() or src in self._failed:
                continue
            try:
                encode(src, dst)
                made += 1
            except Exception as exc:  # a bad file shouldn't stop the rest
                self._failed.add(src)
                log.warning("Couldn't make a preview for %s: %s", src, exc)
        if made:
            log.info("Made %d playback preview(s)", made)
        return made


class SyncPreviews(PreviewMaker):
    """Runs inline; for tests."""

    def kick(self) -> None:
        self.make_missing()
