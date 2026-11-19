"""Song/track operations shared by the web pages and the JSON API."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .audio import InvalidWav, guess_role, track_name_from_filename
from .models import TRACK_ROLES, Section, Song, Track, User
from .security import hash_password
from .storage import delete_song_dir, delete_track_file, save_upload

KEYS = [
    "C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B",
]
KEY_OPTIONS = [""] + KEYS + [k + "m" for k in KEYS]


class ValidationError(ValueError):
    pass


def parse_bpm(value: str | float | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        bpm = float(value)
    except ValueError as exc:
        raise ValidationError("BPM must be a number") from exc
    if not 20 <= bpm <= 400:
        raise ValidationError("BPM must be between 20 and 400")
    return round(bpm, 3)


def parse_time_signature(value: str | None) -> str:
    value = (value or "4/4").strip()
    if not re.fullmatch(r"\d{1,2}/(1|2|4|8|16|32)", value):
        raise ValidationError("Time signature should look like 4/4 or 6/8")
    return value


def parse_timestamp(value: str | float) -> float:
    """Accept seconds ("83.5") or m:ss(.ms) ("1:23.5") or h:mm:ss."""
    text = str(value).strip()
    if not text:
        raise ValidationError("Enter a start time")
    parts = text.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError as exc:
        raise ValidationError("Time should look like 1:23 or 83.5") from exc
    if len(nums) > 3 or any(n < 0 for n in nums):
        raise ValidationError("Time should look like 1:23 or 83.5")
    seconds = 0.0
    for n in nums:
        seconds = seconds * 60 + n
    return round(seconds, 3)


def format_timestamp(seconds: float | None) -> str:
    if seconds is None:
        return ""
    total = max(0.0, float(seconds))
    whole = int(total)
    frac = round(total - whole, 3)
    if frac >= 1:
        whole, frac = whole + 1, 0.0
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    sec = f"{s:02d}"
    if frac:
        sec += f"{frac:.3f}"[1:].rstrip("0")
    return f"{h}:{m:02d}:{sec}" if h else f"{m}:{sec}"


def apply_song_fields(song: Song, *, title, artist, bpm, key, time_signature, notes) -> None:
    title = (title or "").strip()
    if not title:
        raise ValidationError("Title is required")
    key = (key or "").strip()
    if key not in KEY_OPTIONS:
        raise ValidationError("Unknown key")
    song.title = title[:255]
    song.artist = (artist or "").strip()[:255]
    song.bpm = parse_bpm(bpm)
    song.key = key
    song.time_signature = parse_time_signature(time_signature)
    song.notes = (notes or "").strip()


def list_songs(db: Session, user: User, q: str = "") -> list[Song]:
    stmt = select(Song).where(Song.owner_id == user.id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Song.title.ilike(like) | Song.artist.ilike(like))
    return list(db.scalars(stmt.order_by(func.lower(Song.title))))


async def add_tracks(
    db: Session, library_dir: Path, song: Song, uploads: list[UploadFile]
) -> tuple[list[Track], list[str]]:
    """Save each upload as a track. Returns (created tracks, error messages)."""
    created: list[Track] = []
    errors: list[str] = []
    next_pos = max((t.position for t in song.tracks), default=-1) + 1
    for upload in uploads:
        filename = Path(upload.filename or "track.wav").name
        if not filename:
            continue
        try:
            stored, size, sha, info = await save_upload(library_dir, song.id, upload)
        except InvalidWav as exc:
            errors.append(f"{filename}: {exc}")
            continue
        track = Track(
            song=song,
            name=track_name_from_filename(filename)[:255],
            role=guess_role(filename),
            position=next_pos,
            stored_filename=stored,
            original_filename=filename[:255],
            size_bytes=size,
            sha256=sha,
            sample_rate=info.sample_rate,
            channels=info.channels,
            bit_depth=info.bit_depth,
            sample_format=info.sample_format,
            duration_seconds=info.duration_seconds,
        )
        db.add(track)
        created.append(track)
        next_pos += 1
    db.commit()
    return created, errors


def update_track(track: Track, *, name=None, role=None, gain_db=None, pan=None, muted=None) -> None:
    if name is not None:
        name = name.strip()
        if not name:
            raise ValidationError("Track name is required")
        track.name = name[:255]
    if role is not None:
        if role not in TRACK_ROLES:
            raise ValidationError("Unknown track role")
        track.role = role
    if gain_db is not None:
        try:
            g = float(gain_db)
        except ValueError as exc:
            raise ValidationError("Gain must be a number") from exc
        track.gain_db = max(-60.0, min(12.0, g))
    if pan is not None:
        try:
            p = float(pan)
        except ValueError as exc:
            raise ValidationError("Pan must be a number") from exc
        track.pan = max(-1.0, min(1.0, p))
    if muted is not None:
        track.muted = bool(muted)


def move_track(db: Session, track: Track, direction: int) -> None:
    tracks = list(track.song.tracks)
    idx = tracks.index(track)
    swap = idx + direction
    if 0 <= swap < len(tracks):
        tracks[idx], tracks[swap] = tracks[swap], tracks[idx]
    for pos, t in enumerate(tracks):
        t.position = pos
    db.commit()


def delete_track(db: Session, library_dir: Path, track: Track) -> None:
    song_id, stored = track.song_id, track.stored_filename
    db.delete(track)
    db.commit()
    delete_track_file(library_dir, song_id, stored)


def delete_song(db: Session, library_dir: Path, song: Song) -> None:
    song_id = song.id
    db.delete(song)
    db.commit()
    delete_song_dir(library_dir, song_id)


def add_section(db: Session, song: Song, name: str, start) -> Section:
    name = (name or "").strip()
    if not name:
        raise ValidationError("Section name is required")
    section = Section(song=song, name=name[:128], start_seconds=parse_timestamp(start))
    db.add(section)
    db.commit()
    return section


def create_user(db: Session, username: str, password: str, *, display_name: str = "", is_admin=False) -> User:
    username = (username or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{2,64}", username):
        raise ValidationError("Username must be 2-64 letters, numbers, dots, dashes or underscores")
    if len(password or "") < 8:
        raise ValidationError("Password must be at least 8 characters")
    if db.scalar(select(User).where(User.username == username)):
        raise ValidationError("That username is taken")
    user = User(
        username=username,
        display_name=(display_name or "").strip() or username,
        password_hash=hash_password(password),
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    return user


def set_password(db: Session, user: User, password: str) -> None:
    if len(password or "") < 8:
        raise ValidationError("Password must be at least 8 characters")
    user.password_hash = hash_password(password)
    db.commit()
