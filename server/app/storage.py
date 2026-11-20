"""Where stem files live on disk: <data>/library/<song id>/<uuid>.wav"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile

from .audio import WavInfo, read_wav_info

CHUNK = 1024 * 1024


def song_dir(library_dir: Path, song_id: int) -> Path:
    return library_dir / str(song_id)


def track_path(library_dir: Path, song_id: int, stored_filename: str) -> Path:
    return song_dir(library_dir, song_id) / stored_filename


async def save_upload(library_dir: Path, song_id: int, upload: UploadFile) -> tuple[str, int, str, WavInfo]:
    """Stream an upload to disk, validate it as WAV, and return
    (stored filename, size, sha256, wav info). Removes the file if invalid."""
    target_dir = song_dir(library_dir, song_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}.wav"
    partial = target_dir / (stored + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with partial.open("wb") as out:
            while chunk := await upload.read(CHUNK):
                out.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        with partial.open("rb") as fh:
            info = read_wav_info(fh)
        os.replace(partial, target_dir / stored)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return stored, size, digest.hexdigest(), info


def save_fileobj(library_dir: Path, song_id: int, fh: BinaryIO) -> tuple[str, int, str, WavInfo]:
    """Synchronous twin of save_upload, for files pulled out of a ZIP."""
    target_dir = song_dir(library_dir, song_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}.wav"
    partial = target_dir / (stored + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with partial.open("wb") as out:
            while chunk := fh.read(CHUNK):
                out.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        with partial.open("rb") as check:
            info = read_wav_info(check)
        os.replace(partial, target_dir / stored)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return stored, size, digest.hexdigest(), info


def preview_path(library_dir: Path, song_id: int, stored_filename: str) -> Path:
    """The small AAC copy the browser player uses (see previews.py)."""
    return song_dir(library_dir, song_id) / (Path(stored_filename).stem + ".m4a")


def delete_track_file(library_dir: Path, song_id: int, stored_filename: str) -> None:
    track_path(library_dir, song_id, stored_filename).unlink(missing_ok=True)
    preview_path(library_dir, song_id, stored_filename).unlink(missing_ok=True)


def delete_song_dir(library_dir: Path, song_id: int) -> None:
    shutil.rmtree(song_dir(library_dir, song_id), ignore_errors=True)


def copy_track_file(library_dir: Path, from_song: int, stored_filename: str, to_song: int) -> None:
    """Give another song its own copy of a stem. Hard-links when the disk allows it
    (no extra space; stems are never edited in place), otherwise copies."""
    src = track_path(library_dir, from_song, stored_filename)
    dst_dir = song_dir(library_dir, to_song)
    dst_dir.mkdir(parents=True, exist_ok=True)
    pairs = [(src, dst_dir / stored_filename)]
    preview = preview_path(library_dir, from_song, stored_filename)
    if preview.exists():
        pairs.append((preview, preview_path(library_dir, to_song, stored_filename)))
    for a, b in pairs:
        try:
            os.link(a, b)
        except OSError:
            shutil.copy2(a, b)
