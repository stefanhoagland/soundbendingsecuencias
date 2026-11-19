"""Background job: detect sections from a song's guide track."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import sessionmaker

from .guide import click_phase, find_cues, snap_to_bars
from .models import Section, Song
from .storage import track_path

log = logging.getLogger("soundbending.sections")

ACTIVE = ("queued", "running")


class JobRunner:
    """One worker, so only one song is transcribed at a time."""

    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sections")

    def submit(self, fn, *args):
        return self._pool.submit(fn, *args)


def has_guide(song: Song) -> bool:
    return any(t.role == "guide" for t in song.tracks)


def maybe_queue_after_upload(state, db, song: Song) -> bool:
    """Called after stems are added. Queues detection when the song has a guide
    and nobody has typed sections in yet."""
    if not state.settings.auto_sections or not has_guide(song):
        return False
    if any(s.source == "manual" for s in song.sections):
        return False
    return queue(state, db, song, delay=3.0)


def queue(state, db, song: Song, delay: float = 0.0) -> bool:
    if song.sections_status in ACTIVE:
        return False  # one run will pick up every stem uploaded in the meantime
    song.sections_status = "queued"
    song.sections_note = ""
    db.commit()
    state.jobs.submit(run, state, song.id, delay)
    return True


def run(state, song_id: int, delay: float = 0.0) -> None:
    if delay:
        time.sleep(delay)  # let the rest of a multi-file upload land first
    factory: sessionmaker = state.session_factory
    with factory() as db:
        song = db.get(Song, song_id)
        if song is None:
            return
        try:
            guide = next((t for t in song.tracks if t.role == "guide"), None)
            if guide is None:
                song.sections_status, song.sections_note = "no_guide", "No track is marked as Guide."
                db.commit()
                return
            song.sections_status = "running"
            db.commit()
            lib = state.settings.library_dir
            words = state.transcriber.transcribe(track_path(lib, song.id, guide.stored_filename))
            cues = find_cues(words)
            beats = int((song.time_signature or "4/4").split("/")[0] or 4)
            click = next((t for t in song.tracks if t.role == "click"), None)
            phase = click_phase(track_path(lib, song.id, click.stored_filename), song.bpm, beats) if click else 0.0
            found = snap_to_bars(cues, song.bpm, beats, phase, song.duration_seconds)
            for sec in [s for s in song.sections if s.source == "auto"]:
                db.delete(sec)
            db.flush()
            manual_times = {round(s.start_seconds, 1) for s in song.sections if s.source == "manual"}
            for label, t in found:
                if round(t, 1) not in manual_times:
                    db.add(Section(song_id=song.id, name=label, start_seconds=t, source="auto"))
            if found:
                song.sections_status = "done"
                song.sections_note = f"Found {len(found)} section{'s' if len(found) != 1 else ''} in the guide track."
            else:
                song.sections_status = "none"
                song.sections_note = "Didn't hear any section cues in the guide track."
            db.commit()
            log.info("Song %s: %s (%d words heard)", song_id, song.sections_note, len(words))
        except Exception as exc:  # noqa: BLE001 - report on the page instead of crashing the worker
            log.exception("Section detection failed for song %s", song_id)
            db.rollback()
            song = db.get(Song, song_id)
            if song is not None:
                song.sections_status = "failed"
                song.sections_note = f"Couldn't listen to the guide track: {exc}"[:500]
                db.commit()
